from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from bff_control.domains.authentication.contracts import AccessTokenVerificationError
from bff_control.domains.authentication.models import (
    AuthenticatedPrincipal,
    VerifiedAccessToken,
)
from bff_control.domains.authentication.provisioning import SessionProvisioningService
from bff_control.domains.authentication.provisioning_contracts import (
    AccountLinkRequiredError,
    EmailVerificationRequiredError,
    ExternalUserProfileNotFoundError,
    ExternalUserProfileUnavailableError,
    SessionProvisioningAuthenticationError,
)
from bff_control.domains.authentication.provisioning_models import (
    ExternalUserProfile,
    ProvisionedSession,
    ProvisioningIdentity,
)


def _token() -> VerifiedAccessToken:
    now = datetime.now(tz=UTC)
    return VerifiedAccessToken(
        issuer="https://issuer.example",
        subject="user_test",
        provider_session_id="session_test",
        token_id="token_test",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _result() -> ProvisionedSession:
    return ProvisionedSession(
        principal=AuthenticatedPrincipal(
            user_id=UUID("00000000-0000-7000-8000-000000000701"),
            auth_session_id=UUID("00000000-0000-7000-8000-000000000702"),
            email="user@example.test",
            display_name="User",
        ),
        expires_at=datetime.now(tz=UTC) + timedelta(days=7),
        created=True,
    )


class FakeVerifier:
    def __init__(self, result: VerifiedAccessToken | Exception) -> None:
        self.result = result

    async def verify(self, token: str) -> VerifiedAccessToken:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeProfileProvider:
    def __init__(self, result: ExternalUserProfile | Exception) -> None:
        self.result = result
        self.subjects: list[str] = []

    async def fetch_user(self, subject: str) -> ExternalUserProfile:
        self.subjects.append(subject)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeRepository:
    def __init__(
        self,
        *,
        identity: ProvisioningIdentity | None,
        result: ProvisionedSession | Exception,
    ) -> None:
        self.identity = identity
        self.result = result
        self.existing_calls = 0
        self.new_calls = 0

    async def find_identity(
        self,
        token: VerifiedAccessToken,
    ) -> ProvisioningIdentity | None:
        return self.identity

    async def admit_existing_identity(
        self,
        token: VerifiedAccessToken,
        identity: ProvisioningIdentity,
        *,
        ttl_seconds: int,
    ) -> ProvisionedSession:
        self.existing_calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def provision_new_identity(
        self,
        token: VerifiedAccessToken,
        profile: ExternalUserProfile,
        *,
        ttl_seconds: int,
    ) -> ProvisionedSession:
        self.new_calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _profile(*, verified: bool = True) -> ExternalUserProfile:
    return ExternalUserProfile(
        subject="user_test",
        email="user@example.test",
        email_verified=verified,
        display_name="User",
    )


@pytest.mark.asyncio
async def test_existing_identity_skips_profile_lookup() -> None:
    identity = ProvisioningIdentity(
        identity_id=UUID("00000000-0000-7000-8000-000000000711"),
        user_id=UUID("00000000-0000-7000-8000-000000000712"),
        active=True,
    )
    repository = FakeRepository(identity=identity, result=_result())
    profiles = FakeProfileProvider(_profile())
    service = SessionProvisioningService(
        FakeVerifier(_token()),
        repository,
        profiles,
        absolute_ttl_seconds=604_800,
    )

    result = await service.provision("access-token")

    assert result == repository.result
    assert repository.existing_calls == 1
    assert repository.new_calls == 0
    assert profiles.subjects == []


@pytest.mark.asyncio
async def test_new_identity_fetches_trusted_profile() -> None:
    repository = FakeRepository(identity=None, result=_result())
    profiles = FakeProfileProvider(_profile())
    service = SessionProvisioningService(
        FakeVerifier(_token()),
        repository,
        profiles,
        absolute_ttl_seconds=604_800,
    )

    await service.provision("access-token")

    assert profiles.subjects == ["user_test"]
    assert repository.new_calls == 1


@pytest.mark.asyncio
async def test_unverified_email_is_rejected_before_database_creation() -> None:
    repository = FakeRepository(identity=None, result=_result())
    service = SessionProvisioningService(
        FakeVerifier(_token()),
        repository,
        FakeProfileProvider(_profile(verified=False)),
        absolute_ttl_seconds=604_800,
    )

    with pytest.raises(EmailVerificationRequiredError):
        await service.provision("access-token")

    assert repository.new_calls == 0


@pytest.mark.asyncio
async def test_disabled_existing_identity_is_rejected_without_profile_lookup() -> None:
    identity = ProvisioningIdentity(
        identity_id=UUID("00000000-0000-7000-8000-000000000713"),
        user_id=UUID("00000000-0000-7000-8000-000000000714"),
        active=False,
    )
    profiles = FakeProfileProvider(_profile())
    service = SessionProvisioningService(
        FakeVerifier(_token()),
        FakeRepository(identity=identity, result=_result()),
        profiles,
        absolute_ttl_seconds=604_800,
    )

    with pytest.raises(SessionProvisioningAuthenticationError):
        await service.provision("access-token")

    assert profiles.subjects == []


@pytest.mark.asyncio
async def test_invalid_provider_token_is_normalized() -> None:
    service = SessionProvisioningService(
        FakeVerifier(AccessTokenVerificationError("provider detail")),
        FakeRepository(identity=None, result=_result()),
        FakeProfileProvider(_profile()),
        absolute_ttl_seconds=604_800,
    )

    with pytest.raises(SessionProvisioningAuthenticationError):
        await service.provision("access-token")


@pytest.mark.asyncio
async def test_missing_provider_user_is_normalized_as_authentication_failure() -> None:
    service = SessionProvisioningService(
        FakeVerifier(_token()),
        FakeRepository(identity=None, result=_result()),
        FakeProfileProvider(ExternalUserProfileNotFoundError("missing")),
        absolute_ttl_seconds=604_800,
    )

    with pytest.raises(SessionProvisioningAuthenticationError):
        await service.provision("access-token")


@pytest.mark.asyncio
async def test_provider_unavailability_remains_distinguishable() -> None:
    service = SessionProvisioningService(
        FakeVerifier(_token()),
        FakeRepository(identity=None, result=_result()),
        FakeProfileProvider(ExternalUserProfileUnavailableError("down")),
        absolute_ttl_seconds=604_800,
    )

    with pytest.raises(ExternalUserProfileUnavailableError):
        await service.provision("access-token")


@pytest.mark.asyncio
async def test_account_link_required_propagates_from_repository() -> None:
    service = SessionProvisioningService(
        FakeVerifier(_token()),
        FakeRepository(
            identity=None,
            result=AccountLinkRequiredError("account linking required"),
        ),
        FakeProfileProvider(_profile()),
        absolute_ttl_seconds=604_800,
    )

    with pytest.raises(AccountLinkRequiredError):
        await service.provision("access-token")
