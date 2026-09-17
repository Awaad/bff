"""WorkOS AuthKit JWT verification adapter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Final, Protocol

import jwt
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

from bff_control.core.settings import AuthenticationSettings
from bff_control.domains.authentication.contracts import AccessTokenVerificationError
from bff_control.domains.authentication.models import VerifiedAccessToken

WORKOS_SIGNING_ALGORITHMS: Final[tuple[str, ...]] = ("RS256",)
_REQUIRED_CLAIMS: Final[tuple[str, ...]] = (
    "iss",
    "sub",
    "sid",
    "jti",
    "iat",
    "exp",
    "client_id",
)


class SigningKeyClient(Protocol):
    """Minimal signing-key lookup needed by the WorkOS verifier."""

    def get_signing_key(self, kid: str) -> PyJWK: ...


def build_workos_jwks_client(settings: AuthenticationSettings) -> PyJWKClient:
    """Build the bounded, cache-aware JWKS client."""

    return PyJWKClient(
        str(settings.jwks_url),
        cache_keys=False,
        cache_jwk_set=True,
        lifespan=float(settings.jwks_cache_ttl_seconds),
        timeout=float(settings.jwks_request_timeout_seconds),
        cooldown_duration=float(settings.jwks_unknown_kid_cooldown_seconds),
    )


class WorkOSAccessTokenVerifier:
    """Verify AuthKit JWTs and return only provider-neutral trusted claims."""

    def __init__(
        self,
        settings: AuthenticationSettings,
        *,
        signing_keys: SigningKeyClient | None = None,
    ) -> None:
        self._settings = settings
        self._signing_keys = signing_keys or build_workos_jwks_client(settings)

    async def verify(self, token: str) -> VerifiedAccessToken:
        """Verify a token without blocking the async event loop on JWKS I/O."""

        if not token or len(token) > self._settings.max_bearer_token_length:
            raise AccessTokenVerificationError("access token verification failed")

        return await asyncio.to_thread(self._verify_sync, token)

    def _verify_sync(self, token: str) -> VerifiedAccessToken:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            kid = header.get("kid")

            if algorithm not in WORKOS_SIGNING_ALGORITHMS:
                raise AccessTokenVerificationError("access token verification failed")
            if not isinstance(kid, str) or not kid:
                raise AccessTokenVerificationError("access token verification failed")

            signing_key = self._signing_keys.get_signing_key(kid)
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=list(WORKOS_SIGNING_ALGORITHMS),
                issuer=self._settings.issuer,
                leeway=self._settings.jwt_leeway_seconds,
                options={
                    "require": list(_REQUIRED_CLAIMS),
                    "verify_aud": False,
                    "verify_iat": True,
                    "verify_jti": True,
                    "verify_sub": True,
                },
            )
            return self._claims_from_payload(payload)
        except AccessTokenVerificationError:
            raise
        except (PyJWTError, PyJWKClientError, ValueError, OverflowError) as error:
            raise AccessTokenVerificationError("access token verification failed") from error

    def _claims_from_payload(self, payload: dict[str, Any]) -> VerifiedAccessToken:
        client_id = self._required_non_empty_string(payload, "client_id")
        if client_id != self._settings.client_id:
            raise AccessTokenVerificationError("access token verification failed")

        issuer = self._required_non_empty_string(payload, "iss")
        subject = self._required_non_empty_string(payload, "sub")
        provider_session_id = self._required_non_empty_string(payload, "sid")
        token_id = self._required_non_empty_string(payload, "jti")
        issued_at_value = self._required_timestamp(payload, "iat")
        expires_at_value = self._required_timestamp(payload, "exp")

        if expires_at_value <= issued_at_value:
            raise AccessTokenVerificationError("access token verification failed")

        return VerifiedAccessToken(
            issuer=issuer,
            subject=subject,
            provider_session_id=provider_session_id,
            token_id=token_id,
            issued_at=datetime.fromtimestamp(issued_at_value, tz=UTC),
            expires_at=datetime.fromtimestamp(expires_at_value, tz=UTC),
        )

    @staticmethod
    def _required_non_empty_string(payload: dict[str, Any], claim: str) -> str:
        value = payload.get(claim)
        if not isinstance(value, str) or not value:
            raise AccessTokenVerificationError("access token verification failed")
        return value

    @staticmethod
    def _required_timestamp(payload: dict[str, Any], claim: str) -> int:
        value = payload.get(claim)
        if isinstance(value, bool) or not isinstance(value, int):
            raise AccessTokenVerificationError("access token verification failed")
        return value
