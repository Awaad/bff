"""Authentication and local session endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from bff_control.api.dependencies.authentication import require_bearer_token
from bff_control.api.problems.openapi import problem_openapi_response
from bff_control.api.problems.schemas import ProblemCode
from bff_control.domains.authentication.provisioning_contracts import SessionProvisioner
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

router = APIRouter(prefix="/v1/auth", tags=["authentication"])


class ProvisionedUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None


class SessionProvisioningResponse(BaseModel):
    user: ProvisionedUserResponse
    expires_at: datetime


@router.post(
    "/session",
    operation_id="provisionSession",
    response_model=SessionProvisioningResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
        status.HTTP_403_FORBIDDEN: problem_openapi_response(
            ProblemCode.AUTH_EMAIL_VERIFICATION_REQUIRED,
        ),
        status.HTTP_409_CONFLICT: problem_openapi_response(
            ProblemCode.AUTH_ACCOUNT_LINK_REQUIRED,
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: problem_openapi_response(
            ProblemCode.AUTH_PROVIDER_UNAVAILABLE,
        ),
    },
    summary="Provision local authenticated session",
)
async def provision_session(
    request: Request,
    response: Response,
    token: Annotated[str, Depends(require_bearer_token)],
) -> SessionProvisioningResponse:
    provisioner = cast(SessionProvisioner | None, request.app.state.session_provisioner)
    if provisioner is None:
        raise RuntimeError("session provisioner is not configured")
    result = await provisioner.provision(token)
    response.headers["Cache-Control"] = "no-store"
    return SessionProvisioningResponse(
        user=ProvisionedUserResponse(
            id=result.principal.user_id,
            email=result.principal.email,
            display_name=result.principal.display_name,
        ),
        expires_at=result.expires_at,
    )
