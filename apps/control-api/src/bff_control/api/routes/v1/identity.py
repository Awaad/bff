"""Authenticated identity endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from bff_control.api.dependencies.authentication import require_authenticated_principal
from bff_control.api.problems.openapi import problem_openapi_response
from bff_control.api.problems.schemas import ProblemCode
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

router = APIRouter(prefix="/v1", tags=["identity"])


class MeResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None


@router.get(
    "/me",
    operation_id="getMe",
    response_model=MeResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
    },
    summary="Get current user",
)
async def get_me(
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> MeResponse:
    response.headers["Cache-Control"] = "no-store"
    return MeResponse(
        id=principal.user_id,
        email=principal.email,
        display_name=principal.display_name,
    )
