from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from bff_control.core.settings import WorkOSSettings
from pydantic import SecretStr

from scripts.auth.workos_live_probe import (
    ProbeError,
    build_authorization_url,
    decode_unverified_access_token,
    derive_code_challenge,
    exchange_authorization_code,
    validate_loopback_redirect_uri,
    verify_workos_user_lookup,
)


def _unsigned_diagnostic_jwt(payload: dict[str, object]) -> str:
    header: dict[str, object] = {"alg": "none", "typ": "JWT"}

    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{encode(header)}.{encode(payload)}."


def test_pkce_s256_matches_rfc_7636_example() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert derive_code_challenge(verifier) == ("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")


def test_authorization_url_contains_public_client_pkce_contract() -> None:
    url = build_authorization_url(
        api_base_url="https://api.workos.com",
        client_id="client_test",
        redirect_uri="http://127.0.0.1:8787/callback",
        state="state-value",
        code_challenge="challenge-value",
    )
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.workos.com"
    assert parsed.path == "/user_management/authorize"
    assert query == {
        "response_type": ["code"],
        "client_id": ["client_test"],
        "redirect_uri": ["http://127.0.0.1:8787/callback"],
        "state": ["state-value"],
        "provider": ["authkit"],
        "code_challenge_method": ["S256"],
        "code_challenge": ["challenge-value"],
    }


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://127.0.0.1:8787/callback",
        "http://example.com:8787/callback",
        "http://127.0.0.1/callback",
        "http://127.0.0.1:8787/",
        "http://user:pass@127.0.0.1:8787/callback",
        "http://127.0.0.1:8787/callback?token=value",
    ],
)
def test_loopback_redirect_validation_rejects_unsafe_shapes(
    redirect_uri: str,
) -> None:
    with pytest.raises(ProbeError):
        validate_loopback_redirect_uri(redirect_uri)


def test_loopback_redirect_validation_returns_bind_target() -> None:
    assert validate_loopback_redirect_uri(
        "http://127.0.0.1:8787/callback",
    ) == ("127.0.0.1", 8787, "/callback")


def test_unverified_claim_decoder_extracts_only_diagnostic_contract() -> None:
    token = _unsigned_diagnostic_jwt(
        {
            "iss": "https://api.workos.com",
            "sub": "user_test",
            "client_id": "client_test",
            "sid": "session_test",
            "ignored": "value",
        }
    )

    claims = decode_unverified_access_token(token)

    assert claims.issuer == "https://api.workos.com"
    assert claims.subject == "user_test"
    assert claims.client_id == "client_test"
    assert claims.provider_session_id == "session_test"


def test_unverified_claim_decoder_rejects_malformed_token() -> None:
    with pytest.raises(ProbeError):
        decode_unverified_access_token("not-a-jwt")


def test_pkce_exchange_omits_client_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == httpx.URL("https://api.workos.com/user_management/authenticate")
        payload = json.loads(request.content)
        assert payload == {
            "client_id": "client_test",
            "grant_type": "authorization_code",
            "code": "authorization-code",
            "code_verifier": "verifier-value",
        }
        assert "client_secret" not in payload
        return httpx.Response(
            200,
            json={
                "access_token": "header.payload.signature",
                "refresh_token": "must-not-be-used-by-probe",
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        access_token = exchange_authorization_code(
            client=client,
            api_base_url="https://api.workos.com",
            client_id="client_test",
            code="authorization-code",
            code_verifier="verifier-value",
        )

    assert access_token == "header.payload.signature"


def test_workos_user_lookup_uses_server_api_key_and_exact_subject() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == httpx.URL("https://api.workos.com/user_management/users/user_test")
        assert request.headers["authorization"] == "Bearer sk_test_secret"
        return httpx.Response(
            200,
            json={
                "id": "user_test",
                "email": "user@example.test",
                "email_verified": True,
            },
        )

    settings = WorkOSSettings.model_validate(
        {
            "api_key": SecretStr("sk_test_secret"),
            "api_base_url": "https://api.workos.com",
        }
    )
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        user = verify_workos_user_lookup(
            client=client,
            workos_settings=settings,
            subject="user_test",
        )

    assert user.id == "user_test"
    assert user.email_verified is True
