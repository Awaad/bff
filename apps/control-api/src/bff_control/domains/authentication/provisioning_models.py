"""Provider-neutral session-provisioning models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from bff_control.domains.authentication.models import AuthenticatedPrincipal


@dataclass(frozen=True, slots=True)
class ExternalUserProfile:
    """Trusted profile fetched server-side from the authentication provider."""

    subject: str
    email: str
    email_verified: bool
    display_name: str | None


@dataclass(frozen=True, slots=True)
class ProvisioningIdentity:
    """Existing local identity state used before session provisioning."""

    identity_id: UUID
    user_id: UUID
    active: bool


@dataclass(frozen=True, slots=True)
class ProvisionedSession:
    """Result of idempotent local session provisioning."""

    principal: AuthenticatedPrincipal
    expires_at: datetime
    created: bool
