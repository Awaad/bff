#!/usr/bin/env python3
"""Exercise the real WorkOS PKCE flow against the local BFF control API.

This is developer tooling, not an application login surface. Tokens remain only in
process memory and are never printed or written to disk.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from uuid import UUID

import httpx
from bff_control.core.settings import (
    AuthenticationSettings,
    WorkOSSettings,
    get_authentication_settings,
    get_workos_settings,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8787/callback"
DEFAULT_BFF_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_CALLBACK_TIMEOUT_SECONDS = 300.0


class ProbeError(RuntimeError):
    """Expected live-probe failure with safe diagnostic text."""


class DiagnosticAccessTokenClaims(BaseModel):
    """Unverified claims used only to diagnose local configuration."""

    model_config = ConfigDict(extra="ignore")

    issuer: str = Field(alias="iss")
    subject: str = Field(alias="sub")
    client_id: str
    provider_session_id: str = Field(alias="sid")


class WorkOSAuthenticateResponse(BaseModel):
    """Fields required from a successful WorkOS PKCE code exchange."""

    model_config = ConfigDict(extra="ignore")

    access_token: str


class WorkOSUserResponse(BaseModel):
    """Fields required to prove the server-side WorkOS User lookup."""

    model_config = ConfigDict(extra="ignore")

    id: str
    email: str
    email_verified: bool


class BffUserResponse(BaseModel):
    """Public BFF User representation used by the live probe."""

    id: UUID
    email: str
    display_name: str | None


class BffSessionResponse(BaseModel):
    """Local BFF session-provisioning response."""

    user: BffUserResponse
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ProbeConfig:
    """Developer-controlled live-probe configuration."""

    redirect_uri: str
    bff_base_url: str
    callback_timeout_seconds: float
    open_browser: bool


@dataclass(slots=True)
class CallbackCapture:
    """One authorization callback captured by the loopback HTTP server."""

    code: str | None = None
    state: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ProbeSummary:
    """Safe values suitable for terminal output after a successful proof."""

    workos_subject: str
    bff_user_id: UUID
    expires_at: datetime
    email_verified: bool


def generate_code_verifier() -> str:
    """Generate an RFC 7636-compatible high-entropy verifier."""

    return secrets.token_urlsafe(64)


def derive_code_challenge(code_verifier: str) -> str:
    """Derive the S256 PKCE challenge for one verifier."""

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorization_url(
    *,
    api_base_url: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    """Build the WorkOS AuthKit PKCE authorization URL."""

    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "provider": "authkit",
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
        }
    )
    return f"{api_base_url.rstrip('/')}/user_management/authorize?{query}"


def validate_loopback_redirect_uri(redirect_uri: str) -> tuple[str, int, str]:
    """Return host/port/path for a safe local callback URI."""

    parsed = urlsplit(redirect_uri)
    if parsed.scheme != "http":
        raise ProbeError("live probe redirect URI must use http")
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ProbeError("live probe redirect URI must use a loopback hostname")
    if parsed.port is None:
        raise ProbeError("live probe redirect URI must include an explicit port")
    if not parsed.path or parsed.path == "/":
        raise ProbeError("live probe redirect URI must include a callback path")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ProbeError(
            "live probe redirect URI cannot contain credentials, query, or fragment",
        )
    return parsed.hostname, parsed.port, parsed.path


def decode_unverified_access_token(access_token: str) -> DiagnosticAccessTokenClaims:
    """Decode JWT payload for diagnostics only, never for authentication."""

    parts = access_token.split(".")
    if len(parts) != 3:
        raise ProbeError("WorkOS returned an invalid access-token shape")

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        raw_payload = base64.urlsafe_b64decode(payload_segment + padding)
        payload: object = json.loads(raw_payload)
        return DiagnosticAccessTokenClaims.model_validate(payload)
    except (ValueError, ValidationError) as error:
        raise ProbeError("WorkOS access token had invalid diagnostic claims") from error


def _callback_handler(
    expected_path: str,
    capture: CallbackCapture,
) -> type[BaseHTTPRequestHandler]:
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query, keep_blank_values=True)
            capture.code = _single_query_value(params, "code")
            capture.state = _single_query_value(params, "state")
            capture.error = _single_query_value(params, "error")

            body = (
                b"Authentication callback received. "
                b"You can close this tab and return to the terminal."
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return CallbackHandler


def _single_query_value(
    params: dict[str, list[str]],
    key: str,
) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0]


def wait_for_authorization_callback(
    *,
    redirect_uri: str,
    expected_state: str,
    authorization_url: str,
    timeout_seconds: float,
    open_browser: bool,
) -> str:
    """Receive one WorkOS authorization code on a loopback callback."""

    host, port, expected_path = validate_loopback_redirect_uri(redirect_uri)
    capture = CallbackCapture()
    handler = _callback_handler(expected_path, capture)
    deadline = time.monotonic() + timeout_seconds

    with HTTPServer((host, port), handler) as server:
        server.timeout = 1.0

        if open_browser:
            if not webbrowser.open(authorization_url, new=1):
                raise ProbeError(
                    "browser could not be opened; rerun with --print-authorization-url",
                )
        else:
            print("Open this one-time authorization URL in your browser:")
            print(authorization_url)

        while capture.code is None and capture.error is None:
            if time.monotonic() >= deadline:
                raise ProbeError("timed out waiting for WorkOS authorization callback")
            server.handle_request()

    if capture.error is not None:
        raise ProbeError(f"WorkOS authorization failed with error {capture.error!r}")
    if capture.state != expected_state:
        raise ProbeError("WorkOS authorization callback state did not match")
    if capture.code is None:
        raise ProbeError("WorkOS authorization callback did not contain a code")
    return capture.code


def exchange_authorization_code(
    *,
    client: httpx.Client,
    api_base_url: str,
    client_id: str,
    code: str,
    code_verifier: str,
) -> str:
    """Exchange the PKCE authorization code without a client secret."""

    response = client.post(
        f"{api_base_url.rstrip('/')}/user_management/authenticate",
        json={
            "client_id": client_id,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
        },
    )
    if response.status_code != 200:
        raise ProbeError(
            f"WorkOS authorization-code exchange failed with HTTP {response.status_code}",
        )

    try:
        payload = WorkOSAuthenticateResponse.model_validate(response.json())
    except (ValueError, ValidationError) as error:
        raise ProbeError("WorkOS authorization response had an invalid shape") from error
    return payload.access_token


def verify_workos_user_lookup(
    *,
    client: httpx.Client,
    workos_settings: WorkOSSettings,
    subject: str,
) -> WorkOSUserResponse:
    """Prove the configured server API key can retrieve the verified JWT subject."""

    response = client.get(
        (
            f"{str(workos_settings.api_base_url).rstrip('/')}"
            f"/user_management/users/{quote(subject, safe='')}"
        ),
        headers={
            "Authorization": f"Bearer {workos_settings.api_key.get_secret_value()}",
            "Accept": "application/json",
        },
    )
    if response.status_code != 200:
        raise ProbeError(
            f"WorkOS server-side user lookup failed with HTTP {response.status_code}",
        )

    try:
        user = WorkOSUserResponse.model_validate(response.json())
    except (ValueError, ValidationError) as error:
        raise ProbeError("WorkOS user response had an invalid shape") from error

    if user.id != subject:
        raise ProbeError("WorkOS user lookup returned a different subject")
    return user


def verify_bff_readiness(
    *,
    client: httpx.Client,
    bff_base_url: str,
) -> None:
    """Fail before browser authentication if the local BFF is not ready."""

    try:
        live = client.get(f"{bff_base_url.rstrip('/')}/livez")
        ready = client.get(f"{bff_base_url.rstrip('/')}/readyz")
    except httpx.HTTPError as error:
        raise ProbeError("local BFF control API is not reachable") from error

    if live.status_code != 200:
        raise ProbeError(f"BFF liveness failed with HTTP {live.status_code}")
    if ready.status_code != 200:
        raise ProbeError(f"BFF readiness failed with HTTP {ready.status_code}")


def verify_bff_session_flow(
    *,
    client: httpx.Client,
    bff_base_url: str,
    access_token: str,
) -> tuple[BffSessionResponse, BffUserResponse]:
    """Prove local provisioning, natural-key reuse, and authenticated `/v1/me`."""

    headers = {"Authorization": f"Bearer {access_token}"}
    session_url = f"{bff_base_url.rstrip('/')}/v1/auth/session"

    first_response = client.post(session_url, headers=headers)
    _require_bff_success(first_response, "initial session provisioning")
    second_response = client.post(session_url, headers=headers)
    _require_bff_success(second_response, "idempotent session reuse")

    try:
        first = BffSessionResponse.model_validate(first_response.json())
        second = BffSessionResponse.model_validate(second_response.json())
    except (ValueError, ValidationError) as error:
        raise ProbeError("BFF session response had an invalid shape") from error

    if second.user != first.user:
        raise ProbeError("BFF session reuse returned a different local User")
    if second.expires_at != first.expires_at:
        raise ProbeError("BFF session reuse unexpectedly extended local expiry")

    me_response = client.get(
        f"{bff_base_url.rstrip('/')}/v1/me",
        headers=headers,
    )
    _require_bff_success(me_response, "authenticated /v1/me")

    try:
        current_user = BffUserResponse.model_validate(me_response.json())
    except (ValueError, ValidationError) as error:
        raise ProbeError("BFF /v1/me response had an invalid shape") from error

    if current_user != first.user:
        raise ProbeError("BFF /v1/me did not resolve the provisioned local User")

    return first, current_user


def _require_bff_success(response: httpx.Response, action: str) -> None:
    if response.status_code == 200:
        return

    problem_code = _safe_problem_code(response)
    suffix = f" ({problem_code})" if problem_code is not None else ""
    raise ProbeError(
        f"BFF {action} failed with HTTP {response.status_code}{suffix}",
    )


def _safe_problem_code(response: httpx.Response) -> str | None:
    try:
        payload: object = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if not isinstance(code, str):
        return None
    return code


def verify_diagnostic_claims(
    *,
    claims: DiagnosticAccessTokenClaims,
    settings: AuthenticationSettings,
) -> None:
    """Detect exact issuer/client configuration errors before calling BFF."""

    if claims.client_id != settings.client_id:
        raise ProbeError(
            f"access-token client_id does not match BFF_AUTH_CLIENT_ID: {claims.client_id!r}",
        )
    if claims.issuer != settings.issuer:
        raise ProbeError(
            "access-token issuer does not match BFF_AUTH_ISSUER; "
            f"token issuer is {claims.issuer!r}",
        )


def run_probe(config: ProbeConfig) -> ProbeSummary:
    """Run the live external-provider proof without persisting provider tokens."""

    auth_settings = get_authentication_settings()
    workos_settings = get_workos_settings()
    api_base_url = str(workos_settings.api_base_url).rstrip("/")

    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        verify_bff_readiness(
            client=client,
            bff_base_url=config.bff_base_url,
        )

        code_verifier = generate_code_verifier()
        state = secrets.token_urlsafe(32)
        authorization_url = build_authorization_url(
            api_base_url=api_base_url,
            client_id=auth_settings.client_id,
            redirect_uri=config.redirect_uri,
            state=state,
            code_challenge=derive_code_challenge(code_verifier),
        )
        code = wait_for_authorization_callback(
            redirect_uri=config.redirect_uri,
            expected_state=state,
            authorization_url=authorization_url,
            timeout_seconds=config.callback_timeout_seconds,
            open_browser=config.open_browser,
        )

        access_token = exchange_authorization_code(
            client=client,
            api_base_url=api_base_url,
            client_id=auth_settings.client_id,
            code=code,
            code_verifier=code_verifier,
        )
        claims = decode_unverified_access_token(access_token)
        verify_diagnostic_claims(
            claims=claims,
            settings=auth_settings,
        )

        workos_user = verify_workos_user_lookup(
            client=client,
            workos_settings=workos_settings,
            subject=claims.subject,
        )
        session, current_user = verify_bff_session_flow(
            client=client,
            bff_base_url=config.bff_base_url,
            access_token=access_token,
        )

    return ProbeSummary(
        workos_subject=claims.subject,
        bff_user_id=current_user.id,
        expires_at=session.expires_at,
        email_verified=workos_user.email_verified,
    )


def parse_args() -> ProbeConfig:
    parser = argparse.ArgumentParser(
        description="Exercise WorkOS PKCE against the local BFF API.",
    )
    parser.add_argument(
        "--redirect-uri",
        default=DEFAULT_REDIRECT_URI,
    )
    parser.add_argument(
        "--bff-base-url",
        default=DEFAULT_BFF_BASE_URL,
    )
    parser.add_argument(
        "--callback-timeout-seconds",
        type=float,
        default=DEFAULT_CALLBACK_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--print-authorization-url",
        action="store_true",
        help="Print the one-time URL instead of opening the default browser.",
    )
    args = parser.parse_args()

    if args.callback_timeout_seconds <= 0:
        parser.error("--callback-timeout-seconds must be greater than zero")

    return ProbeConfig(
        redirect_uri=str(args.redirect_uri),
        bff_base_url=str(args.bff_base_url),
        callback_timeout_seconds=float(args.callback_timeout_seconds),
        open_browser=not bool(args.print_authorization_url),
    )


def main() -> int:
    try:
        summary = run_probe(parse_args())
    except (ProbeError, ValidationError) as error:
        print(f"FAIL: {error}")
        return 1

    print("PASS: WorkOS PKCE authorization-code flow")
    print("PASS: access-token issuer/client configuration")
    print("PASS: WorkOS server-side User lookup")
    print("PASS: BFF durable session provisioning")
    print("PASS: BFF same-sid idempotent reuse without TTL extension")
    print("PASS: authenticated /v1/me")
    print(f"WorkOS subject: {summary.workos_subject}")
    print(f"BFF user id: {summary.bff_user_id}")
    print(f"Local session expires at: {summary.expires_at.isoformat()}")
    print(f"WorkOS email verified: {summary.email_verified}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
