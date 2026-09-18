"""Session-provisioning domain interfaces."""

from __future__ import annotations

from typing import Protocol

from bff_control.domains.authentication.models import VerifiedAccessToken
from bff_control.domains.authentication.provisioning_models import (
    ExternalUserProfile,
    ProvisionedSession,
    ProvisioningIdentity,
)


class SessionProvisioningAuthenticationError(Exception):
    """Raised when verified evidence cannot establish local admission."""


class EmailVerificationRequiredError(Exception):
    """Raised when first-time provisioning lacks a verified provider email."""


class AccountLinkRequiredError(Exception):
    """Raised when a verified email collides with an existing BFF User."""


class ExternalUserProfileNotFoundError(Exception):
    """Raised when the verified provider subject no longer resolves to a User."""


class ExternalUserProfileUnavailableError(Exception):
    """Raised when trusted provider profile retrieval is temporarily unavailable."""


class ExternalUserProfileProvider(Protocol):
    """Fetch trusted provider profile data by already verified subject."""

    async def fetch_user(self, subject: str) -> ExternalUserProfile: ...


class SessionProvisioningRepository(Protocol):
    """Persist or reuse durable BFF session admission state."""

    async def find_identity(
        self,
        token: VerifiedAccessToken,
    ) -> ProvisioningIdentity | None: ...

    async def admit_existing_identity(
        self,
        token: VerifiedAccessToken,
        identity: ProvisioningIdentity,
        *,
        ttl_seconds: int,
    ) -> ProvisionedSession: ...

    async def provision_new_identity(
        self,
        token: VerifiedAccessToken,
        profile: ExternalUserProfile,
        *,
        ttl_seconds: int,
    ) -> ProvisionedSession: ...


class SessionProvisioner(Protocol):
    """Verify provider evidence and establish durable local session admission."""

    async def provision(self, token: str) -> ProvisionedSession: ...
