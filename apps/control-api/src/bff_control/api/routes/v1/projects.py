"""Authenticated Project endpoints nested under a Workspace."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from json import JSONDecodeError
from typing import Annotated, cast
from uuid import UUID

from bff_control.api.context import require_request_context
from bff_control.api.dependencies.authentication import require_authenticated_principal
from bff_control.api.problems.openapi import problem_openapi_response
from bff_control.api.problems.schemas import ProblemCode, ProblemDetail
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from bff_control.domains.projects.contracts import ProjectManager
from bff_control.domains.projects.models import Project, ProjectPageCursor, ProjectStatus
from bff_control.domains.projects.policies import (
    DEFAULT_PROJECT_PAGE_LIMIT,
    MAX_PROJECT_NAME_LENGTH,
    MAX_PROJECT_PAGE_LIMIT,
    normalize_project_name,
)
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator

router = APIRouter(
    prefix="/v1/workspaces/{workspace_id}/projects",
    tags=["projects"],
)

_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 512


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_PROJECT_NAME_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_project_name(value)


class ProjectResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    next_cursor: str | None


def _project_service(request: Request) -> ProjectManager:
    return cast(ProjectManager, request.app.state.project_service)


def _response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.project_id,
        workspace_id=project.workspace_id,
        name=project.name,
        status=project.status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
    )


def _encode_cursor(cursor: ProjectPageCursor | None) -> str | None:
    if cursor is None:
        return None
    payload = json.dumps(
        {
            "created_at": cursor.created_at.isoformat(),
            "id": str(cursor.project_id),
            "v": _CURSOR_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str | None) -> ProjectPageCursor | None:
    if value is None:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded.decode())
        if not isinstance(payload, dict) or set(payload) != {"created_at", "id", "v"}:
            raise ValueError("cursor payload has an invalid shape")
        if payload["v"] != _CURSOR_VERSION:
            raise ValueError("cursor version is unsupported")
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError("cursor timestamp must include an offset")
        project_id = UUID(payload["id"])
    except (
        binascii.Error,
        JSONDecodeError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "cursor"),
                    "msg": "Value is invalid.",
                    "input": value,
                    "ctx": {"error": exc},
                }
            ]
        ) from exc
    return ProjectPageCursor(created_at=created_at, project_id=project_id)


@router.post(
    "",
    operation_id="createProject",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Project created",
            "headers": {
                "Location": {
                    "description": "Relative URI of the created Project.",
                    "schema": {"type": "string"},
                }
            },
        },
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
        status.HTTP_403_FORBIDDEN: problem_openapi_response(
            ProblemCode.WORKSPACE_PERMISSION_DENIED,
        ),
        status.HTTP_404_NOT_FOUND: problem_openapi_response(
            ProblemCode.WORKSPACE_NOT_FOUND,
        ),
        status.HTTP_409_CONFLICT: problem_openapi_response(
            ProblemCode.WORKSPACE_NOT_ACTIVE,
        ),
    },
    summary="Create project",
)
async def create_project(
    workspace_id: UUID,
    payload: CreateProjectRequest,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ProjectResponse:
    context = require_request_context(request)
    project = await _project_service(request).create_project(
        user_id=principal.user_id,
        auth_session_id=principal.auth_session_id,
        workspace_id=workspace_id,
        name=payload.name,
        request_id=context.request_id,
        trace_id=context.trace_id,
    )
    response.headers["Location"] = f"/v1/workspaces/{workspace_id}/projects/{project.project_id}"
    response.headers["Cache-Control"] = "no-store"
    return _response(project)


@router.get(
    "",
    operation_id="listProjects",
    response_model=ProjectListResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
        status.HTTP_404_NOT_FOUND: problem_openapi_response(
            ProblemCode.WORKSPACE_NOT_FOUND,
        ),
    },
    summary="List projects",
)
async def list_projects(
    workspace_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
    limit: Annotated[int, Query(ge=1, le=MAX_PROJECT_PAGE_LIMIT)] = (DEFAULT_PROJECT_PAGE_LIMIT),
    cursor: Annotated[str | None, Query(max_length=_MAX_CURSOR_LENGTH)] = None,
) -> ProjectListResponse:
    page = await _project_service(request).list_projects(
        user_id=principal.user_id,
        workspace_id=workspace_id,
        cursor=_decode_cursor(cursor),
        limit=limit,
    )
    response.headers["Cache-Control"] = "no-store"
    return ProjectListResponse(
        items=[_response(project) for project in page.items],
        next_cursor=_encode_cursor(page.next_cursor),
    )


@router.get(
    "/{project_id}",
    operation_id="getProject",
    response_model=ProjectResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
        status.HTTP_404_NOT_FOUND: {
            "model": ProblemDetail,
            "description": "Workspace or Project not found",
        },
    },
    summary="Get project",
)
async def get_project(
    workspace_id: UUID,
    project_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ProjectResponse:
    project = await _project_service(request).get_project(
        user_id=principal.user_id,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _response(project)
