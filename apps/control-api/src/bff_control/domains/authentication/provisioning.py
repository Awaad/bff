"""Durable authentication-session provisioning service."""

from __future__ import annotations

from bff_control.domains.authentication.contracts import (
    AccessTokenVerificationError,
    AccessTokenVerifier,
)
from bff_control.domains.authentication.provisioning_contracts import (
    EmailVerificationRequiredError,
    ExternalUserProfileNotFoundError,
    ExternalUserProfileProvider,
    ExternalUserProfileUnavailableError,
    SessionProvisioningAuthenticationError,
    SessionProvisioningRepository,
)
from bff_control.domains.authentication.provisioning_models import ProvisionedSession


class SessionProvisioningService:
    """Provision local admission from cryptographically verified provider evidence."""

    def __init__(
        self,
        verifier: AccessTokenVerifier,
        repository: SessionProvisioningRepository,
        profile_provider: ExternalUserProfileProvider,
        *,
        absolute_ttl_seconds: int,
    ) -> None:
        if absolute_ttl_seconds <= 0:
            raise ValueError("absolute_ttl_seconds must be positive")

        self._verifier = verifier
        self._repository = repository
        self._profile_provider = profile_provider
        self._absolute_ttl_seconds = absolute_ttl_seconds

    async def provision(self, token: str) -> ProvisionedSession:
        """Create or reuse one durable local admission."""

        try:
            verified = await self._verifier.verify(token)
        except AccessTokenVerificationError as error:
            raise SessionProvisioningAuthenticationError(
                "session provisioning authentication failed",
            ) from error

        identity = await self._repository.find_identity(verified)
        if identity is not None:
            if not identity.active:
                raise SessionProvisioningAuthenticationError(
                    "session provisioning authentication failed",
                )
            return await self._repository.admit_existing_identity(
                verified,
                identity,
                ttl_seconds=self._absolute_ttl_seconds,
            )

        try:
            profile = await self._profile_provider.fetch_user(verified.subject)
        except ExternalUserProfileNotFoundError as error:
            raise SessionProvisioningAuthenticationError(
                "session provisioning authentication failed",
            ) from error
        except ExternalUserProfileUnavailableError:
            raise

        if profile.subject != verified.subject:
            raise ExternalUserProfileUnavailableError(
                "provider profile subject mismatch",
            )

        if not profile.email_verified:
            raise EmailVerificationRequiredError("verified email required")

        return await self._repository.provision_new_identity(
            verified,
            profile,
            ttl_seconds=self._absolute_ttl_seconds,
        )
