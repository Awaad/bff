"""Authenticated Workspace endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from bff_control.api.context import require_request_context
from bff_control.api.dependencies.authentication import require_authenticated_principal
from bff_control.api.problems.openapi import problem_openapi_response
from bff_control.api.problems.schemas import ProblemCode
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from bff_control.domains.workspaces.contracts import WorkspaceManager
from bff_control.domains.workspaces.models import (
    WorkspaceAccess,
    WorkspaceRole,
    WorkspaceStatus,
)
from bff_control.domains.workspaces.policies import (
    MAX_WORKSPACE_NAME_LENGTH,
    normalize_workspace_name,
)
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_WORKSPACE_NAME_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_workspace_name(value)


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    status: WorkspaceStatus
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceResponse]


def _workspace_service(request: Request) -> WorkspaceManager:
    return cast(WorkspaceManager, request.app.state.workspace_service)


def _response(access: WorkspaceAccess) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=access.workspace_id,
        name=access.name,
        status=access.status,
        role=access.role,
        created_at=access.created_at,
        updated_at=access.updated_at,
    )


@router.post(
    "",
    operation_id="createWorkspace",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Workspace created",
            "headers": {
                "Location": {
                    "description": "Relative URI of the created Workspace.",
                    "schema": {"type": "string"},
                }
            },
        },
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
    },
    summary="Create workspace",
)
async def create_workspace(
    payload: CreateWorkspaceRequest,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> WorkspaceResponse:
    context = require_request_context(request)
    access = await _workspace_service(request).create_workspace(
        user_id=principal.user_id,
        auth_session_id=principal.auth_session_id,
        name=payload.name,
        request_id=context.request_id,
        trace_id=context.trace_id,
    )
    response.headers["Location"] = f"/v1/workspaces/{access.workspace_id}"
    response.headers["Cache-Control"] = "no-store"
    return _response(access)


@router.get(
    "",
    operation_id="listWorkspaces",
    response_model=WorkspaceListResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
    },
    summary="List workspaces",
)
async def list_workspaces(
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> WorkspaceListResponse:
    accesses = await _workspace_service(request).list_workspaces(principal.user_id)
    response.headers["Cache-Control"] = "no-store"
    return WorkspaceListResponse(items=[_response(access) for access in accesses])


@router.get(
    "/{workspace_id}",
    operation_id="getWorkspace",
    response_model=WorkspaceResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
        status.HTTP_404_NOT_FOUND: problem_openapi_response(
            ProblemCode.WORKSPACE_NOT_FOUND,
        ),
    },
    summary="Get workspace",
)
async def get_workspace(
    workspace_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> WorkspaceResponse:
    access = await _workspace_service(request).get_workspace(
        user_id=principal.user_id,
        workspace_id=workspace_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _response(access)
