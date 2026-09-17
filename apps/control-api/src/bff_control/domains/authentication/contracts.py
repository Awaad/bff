"""Authentication domain interfaces."""

from __future__ import annotations

from typing import Protocol

from bff_control.domains.authentication.models import (
    AuthenticatedPrincipal,
    VerifiedAccessToken,
)


class AccessTokenVerificationError(Exception):
    """Raised when external access-token evidence cannot be trusted."""


class PrincipalAuthenticationError(Exception):
    """Raised when token evidence cannot establish an admitted BFF principal."""


class AccessTokenVerifier(Protocol):
    """Verify external bearer credentials without authorizing BFF resources."""

    async def verify(self, token: str) -> VerifiedAccessToken: ...


class PrincipalRepository(Protocol):
    """Resolve trusted token evidence against durable BFF admission state."""

    async def resolve_active_principal(
        self,
        token: VerifiedAccessToken,
    ) -> AuthenticatedPrincipal | None: ...


class PrincipalAuthenticator(Protocol):
    """Establish an admitted BFF principal from one bearer token."""

    async def authenticate(self, token: str) -> AuthenticatedPrincipal: ...
