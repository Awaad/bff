"""HTTP authentication dependencies."""

from __future__ import annotations

from typing import Annotated, cast

from bff_control.api.problems.exceptions import ProblemException
from bff_control.api.problems.schemas import ProblemCode
from bff_control.domains.authentication.contracts import PrincipalAuthenticator
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_BEARER = HTTPBearer(auto_error=False)


async def require_bearer_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_BEARER),
    ],
) -> str:
    """Return one syntactically present bearer token."""

    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise ProblemException(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


async def require_authenticated_principal(
    request: Request,
    token: Annotated[str, Depends(require_bearer_token)],
) -> AuthenticatedPrincipal:
    """Resolve one bearer credential to an admitted internal BFF principal."""

    authenticator = cast(PrincipalAuthenticator, request.app.state.authenticator)
    return await authenticator.authenticate(token)
