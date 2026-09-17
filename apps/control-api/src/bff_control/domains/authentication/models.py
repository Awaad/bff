"""Provider-neutral authenticated principal and token evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class VerifiedAccessToken:
    """Claims trusted only after provider signature/policy verification."""

    issuer: str
    subject: str
    provider_session_id: str
    token_id: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Internal BFF principal established after durable session admission."""

    user_id: UUID
    auth_session_id: UUID
    email: str
    display_name: str | None
