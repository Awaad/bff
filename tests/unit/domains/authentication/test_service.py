from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from bff_control.domains.authentication.contracts import (
    AccessTokenVerificationError,
    PrincipalAuthenticationError,
)
from bff_control.domains.authentication.models import (
    AuthenticatedPrincipal,
    VerifiedAccessToken,
)
from bff_control.domains.authentication.service import AuthenticationService

TOKEN = "verified-token"


def _verified_token() -> VerifiedAccessToken:
    now = datetime.now(tz=UTC)
    return VerifiedAccessToken(
        issuer="https://issuer.example",
        subject="subject",
        provider_session_id="provider-session",
        token_id="token-id",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=UUID("00000000-0000-7000-8000-000000000501"),
        auth_session_id=UUID("00000000-0000-7000-8000-000000000502"),
        email="user@example.test",
        display_name="User",
    )


class FakeVerifier:
    def __init__(
        self,
        *,
        result: VerifiedAccessToken | None = None,
        error: AccessTokenVerificationError | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.tokens: list[str] = []

    async def verify(self, token: str) -> VerifiedAccessToken:
        self.tokens.append(token)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("fake verifier requires a result or error")
        return self.result


class FakeRepository:
    def __init__(
        self,
        *,
        result: AuthenticatedPrincipal | None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.tokens: list[VerifiedAccessToken] = []

    async def resolve_active_principal(
        self,
        token: VerifiedAccessToken,
    ) -> AuthenticatedPrincipal | None:
        self.tokens.append(token)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_authenticate_returns_admitted_principal() -> None:
    verified = _verified_token()
    principal = _principal()
    verifier = FakeVerifier(result=verified)
    repository = FakeRepository(result=principal)
    service = AuthenticationService(verifier, repository)

    result = await service.authenticate(TOKEN)

    assert result == principal
    assert verifier.tokens == [TOKEN]
    assert repository.tokens == [verified]


@pytest.mark.asyncio
async def test_verification_failure_is_normalized_without_repository_lookup() -> None:
    verifier = FakeVerifier(error=AccessTokenVerificationError("provider detail"))
    repository = FakeRepository(result=None)
    service = AuthenticationService(verifier, repository)

    with pytest.raises(PrincipalAuthenticationError, match="authentication failed"):
        await service.authenticate(TOKEN)

    assert repository.tokens == []


@pytest.mark.asyncio
async def test_missing_local_admission_is_normalized() -> None:
    verifier = FakeVerifier(result=_verified_token())
    repository = FakeRepository(result=None)
    service = AuthenticationService(verifier, repository)

    with pytest.raises(PrincipalAuthenticationError, match="authentication failed"):
        await service.authenticate(TOKEN)


@pytest.mark.asyncio
async def test_repository_failures_are_not_misreported_as_authentication_failures() -> None:
    verifier = FakeVerifier(result=_verified_token())
    repository = FakeRepository(
        result=None,
        error=RuntimeError("database unavailable"),
    )
    service = AuthenticationService(verifier, repository)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.authenticate(TOKEN)
