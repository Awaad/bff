"""Authenticated current-user endpoint."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from bff_control.api.authentication import (
    AuthenticationErrorResponse,
    require_authenticated_principal,
)
from bff_control.domains.authentication.models import AuthenticatedPrincipal

router = APIRouter(prefix="/v1", tags=["identity"])


class MeResponse(BaseModel):
    """Current authenticated BFF user."""

    id: UUID
    email: str
    display_name: str | None


@router.get(
    "/me",
    operation_id="getMe",
    response_model=MeResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": AuthenticationErrorResponse,
            "description": "Authentication required",
        },
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
    """Return the BFF user established by token verification and local admission."""

    response.headers["Cache-Control"] = "no-store"
    return MeResponse(
        id=principal.user_id,
        email=principal.email,
        display_name=principal.display_name,
    )
