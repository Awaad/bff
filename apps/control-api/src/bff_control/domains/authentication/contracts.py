"""Authentication domain interfaces."""

from __future__ import annotations

from typing import Protocol

from bff_control.domains.authentication.models import VerifiedAccessToken


class AccessTokenVerificationError(Exception):
    """Raised when external access-token evidence cannot be trusted."""


class AccessTokenVerifier(Protocol):
    """Verify external bearer credentials without authorizing BFF resources."""

    async def verify(self, token: str) -> VerifiedAccessToken: ...
