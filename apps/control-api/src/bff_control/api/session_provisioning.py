"""Public-client local session provisioning endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Never, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from bff_control.domains.authentication.provisioning_contracts import (
    AccountLinkRequiredError,
    EmailVerificationRequiredError,
    ExternalUserProfileUnavailableError,
    SessionProvisioner,
    SessionProvisioningAuthenticationError,
)

router = APIRouter(prefix="/v1/auth", tags=["authentication"])
_BEARER = HTTPBearer(auto_error=False)


class ProvisionedUserResponse(BaseModel):
    """Public BFF User fields returned after local admission."""

    id: UUID
    email: str
    display_name: str | None


class SessionProvisioningResponse(BaseModel):
    """Idempotent local admission result."""

    user: ProvisionedUserResponse
    expires_at: datetime


class AuthenticationErrorResponse(BaseModel):
    detail: Literal["invalid authentication credentials"]


class EmailVerificationRequiredResponse(BaseModel):
    detail: Literal["email verification required"]


class AccountLinkRequiredResponse(BaseModel):
    detail: Literal["account linking required"]


class AuthenticationServiceUnavailableResponse(BaseModel):
    detail: Literal["authentication service unavailable"]


def _raise_unauthorized() -> Never:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post(
    "/session",
    operation_id="provisionSession",
    response_model=SessionProvisioningResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": AuthenticationErrorResponse,
            "description": "Authentication failed",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": EmailVerificationRequiredResponse,
            "description": "Verified email required for first provisioning",
        },
        status.HTTP_409_CONFLICT: {
            "model": AccountLinkRequiredResponse,
            "description": "Existing BFF account requires explicit linking",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": AuthenticationServiceUnavailableResponse,
            "description": "Authentication provider temporarily unavailable",
        },
    },
    summary="Provision local authenticated session",
)
async def provision_session(
    request: Request,
    response: Response,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_BEARER),
    ],
) -> SessionProvisioningResponse:
    """Create or reuse BFF admission from a verified provider bearer token."""

    if credentials is None or credentials.scheme.casefold() != "bearer":
        _raise_unauthorized()

    provisioner = cast(SessionProvisioner | None, request.app.state.session_provisioner)
    if provisioner is None:
        raise RuntimeError("session provisioner is not configured")

    try:
        result = await provisioner.provision(credentials.credentials)
    except SessionProvisioningAuthenticationError:
        _raise_unauthorized()
    except EmailVerificationRequiredError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email verification required",
        ) from error
    except AccountLinkRequiredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="account linking required",
        ) from error
    except ExternalUserProfileUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication service unavailable",
        ) from error

    response.headers["Cache-Control"] = "no-store"
    return SessionProvisioningResponse(
        user=ProvisionedUserResponse(
            id=result.principal.user_id,
            email=result.principal.email,
            display_name=result.principal.display_name,
        ),
        expires_at=result.expires_at,
    )
