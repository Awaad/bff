"""HTTP authentication adapter."""

from __future__ import annotations

from typing import Annotated, Literal, Never, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from bff_control.domains.authentication.contracts import (
    PrincipalAuthenticationError,
    PrincipalAuthenticator,
)
from bff_control.domains.authentication.models import AuthenticatedPrincipal

_BEARER = HTTPBearer(auto_error=False)


class AuthenticationErrorResponse(BaseModel):
    """Stable public authentication failure shape."""

    detail: Literal["invalid authentication credentials"]


def _raise_unauthorized() -> Never:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_authenticated_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_BEARER),
    ],
) -> AuthenticatedPrincipal:
    """Resolve one bearer credential to an admitted internal BFF principal."""

    if credentials is None or credentials.scheme.casefold() != "bearer":
        _raise_unauthorized()

    authenticator = cast(PrincipalAuthenticator, request.app.state.authenticator)

    try:
        return await authenticator.authenticate(credentials.credentials)
    except PrincipalAuthenticationError:
        _raise_unauthorized()
