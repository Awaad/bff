"""Authentication domain service."""

from __future__ import annotations

from bff_control.domains.authentication.contracts import (
    AccessTokenVerificationError,
    AccessTokenVerifier,
    PrincipalAuthenticationError,
    PrincipalRepository,
)
from bff_control.domains.authentication.models import AuthenticatedPrincipal


class AuthenticationService:
    """Verify provider evidence and enforce durable local session admission."""

    def __init__(
        self,
        verifier: AccessTokenVerifier,
        repository: PrincipalRepository,
    ) -> None:
        self._verifier = verifier
        self._repository = repository

    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        """Return an admitted principal or one normalized authentication failure."""

        try:
            verified = await self._verifier.verify(token)
        except AccessTokenVerificationError as error:
            raise PrincipalAuthenticationError("authentication failed") from error

        principal = await self._repository.resolve_active_principal(verified)
        if principal is None:
            raise PrincipalAuthenticationError("authentication failed")

        return principal
