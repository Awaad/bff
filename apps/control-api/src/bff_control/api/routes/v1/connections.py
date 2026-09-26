"""Authenticated Connection endpoints nested under a Workspace."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from json import JSONDecodeError
from typing import Annotated, Any, cast
from uuid import UUID

from bff_control.api.context import require_request_context
from bff_control.api.dependencies.authentication import require_authenticated_principal
from bff_control.api.problems.openapi import problem_openapi_response
from bff_control.api.problems.schemas import ProblemCode, ProblemDetail
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from bff_control.domains.connections.contracts import ConnectionManager
from bff_control.domains.connections.models import (
    Connection,
    ConnectionAccessMode,
    ConnectionAccessPolicy,
    ConnectionDraft,
    ConnectionLifecycleAction,
    ConnectionPageCursor,
    ConnectionRevision,
    ConnectionRevisionMetadata,
    ConnectionStatus,
)
from bff_control.domains.connections.policies import (
    DEFAULT_CONNECTION_PAGE_LIMIT,
    DEFAULT_CONNECTION_REVISION_PAGE_LIMIT,
    MAX_CONNECTION_NAME_LENGTH,
    MAX_CONNECTION_PAGE_LIMIT,
    MAX_CONNECTION_REVISION_PAGE_LIMIT,
    MAX_SELECTED_PROJECTS,
    normalize_access_policy,
    normalize_connection_name,
    normalize_provider_key,
)
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator, model_validator

router = APIRouter(
    prefix="/v1/workspaces/{workspace_id}/connections",
    tags=["connections"],
)

_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 512
_MAX_PROVIDER_KEY_LENGTH = 64


class ConnectionAccessRequest(BaseModel):
    mode: ConnectionAccessMode
    project_ids: list[UUID] = Field(default_factory=list, max_length=MAX_SELECTED_PROJECTS)

    @model_validator(mode="after")
    def validate_policy(self) -> ConnectionAccessRequest:
        normalize_access_policy(self.mode, self.project_ids)
        return self

    def to_domain(self) -> ConnectionAccessPolicy:
        return normalize_access_policy(self.mode, self.project_ids)


class CreateConnectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_CONNECTION_NAME_LENGTH)
    provider_key: str = Field(min_length=1, max_length=_MAX_PROVIDER_KEY_LENGTH)
    access: ConnectionAccessRequest

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_connection_name(value)

    @field_validator("provider_key")
    @classmethod
    def validate_provider_key(cls, value: str) -> str:
        return normalize_provider_key(value)


class RenameConnectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_CONNECTION_NAME_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_connection_name(value)


class PutConnectionDraftRequest(BaseModel):
    configuration: dict[str, object]


class ConnectionAccessResponse(BaseModel):
    mode: ConnectionAccessMode
    project_ids: list[UUID]


class ConnectionResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    provider_key: str
    access: ConnectionAccessResponse
    status: ConnectionStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ConnectionListResponse(BaseModel):
    items: list[ConnectionResponse]
    next_cursor: str | None


class ConnectionDraftResponse(BaseModel):
    connection_id: UUID
    workspace_id: UUID
    configuration: dict[str, object]
    updated_by_user_id: UUID | None
    updated_at: datetime


class ConnectionRevisionMetadataResponse(BaseModel):
    id: UUID
    connection_id: UUID
    workspace_id: UUID
    revision_number: int
    definition_schema_version: int
    config_hash: str
    created_by_user_id: UUID | None
    created_at: datetime


class ConnectionRevisionResponse(ConnectionRevisionMetadataResponse):
    configuration: dict[str, object]


class ConnectionRevisionListResponse(BaseModel):
    items: list[ConnectionRevisionMetadataResponse]
    next_before_revision: int | None


def _connection_service(request: Request) -> ConnectionManager:
    return cast(ConnectionManager, request.app.state.connection_service)


def _connection_response(connection: Connection) -> ConnectionResponse:
    return ConnectionResponse(
        id=connection.connection_id,
        workspace_id=connection.workspace_id,
        name=connection.name,
        provider_key=connection.provider_key,
        access=ConnectionAccessResponse(
            mode=connection.access_policy.mode,
            project_ids=list(connection.access_policy.project_ids),
        ),
        status=connection.status,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
        archived_at=connection.archived_at,
    )


def _draft_response(draft: ConnectionDraft) -> ConnectionDraftResponse:
    return ConnectionDraftResponse(
        connection_id=draft.connection_id,
        workspace_id=draft.workspace_id,
        configuration=draft.configuration,
        updated_by_user_id=draft.updated_by_user_id,
        updated_at=draft.updated_at,
    )


def _revision_metadata_response(
    revision: ConnectionRevisionMetadata,
) -> ConnectionRevisionMetadataResponse:
    return ConnectionRevisionMetadataResponse(
        id=revision.revision_id,
        connection_id=revision.connection_id,
        workspace_id=revision.workspace_id,
        revision_number=revision.revision_number,
        definition_schema_version=revision.definition_schema_version,
        config_hash=revision.config_hash_hex,
        created_by_user_id=revision.created_by_user_id,
        created_at=revision.created_at,
    )


def _revision_response(revision: ConnectionRevision) -> ConnectionRevisionResponse:
    metadata = revision.metadata
    return ConnectionRevisionResponse(
        id=metadata.revision_id,
        connection_id=metadata.connection_id,
        workspace_id=metadata.workspace_id,
        revision_number=metadata.revision_number,
        definition_schema_version=metadata.definition_schema_version,
        config_hash=metadata.config_hash_hex,
        created_by_user_id=metadata.created_by_user_id,
        created_at=metadata.created_at,
        configuration=revision.configuration,
    )


def _encode_cursor(cursor: ConnectionPageCursor | None) -> str | None:
    if cursor is None:
        return None
    payload = json.dumps(
        {
            "created_at": cursor.created_at.isoformat(),
            "id": str(cursor.connection_id),
            "v": _CURSOR_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str | None) -> ConnectionPageCursor | None:
    if value is None:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(decoded.decode())
        if not isinstance(payload, dict) or set(payload) != {"created_at", "id", "v"}:
            raise ValueError("cursor payload has an invalid shape")
        if payload["v"] != _CURSOR_VERSION:
            raise ValueError("cursor version is unsupported")
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError("cursor timestamp must include an offset")
        connection_id = UUID(payload["id"])
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
    return ConnectionPageCursor(
        created_at=created_at,
        connection_id=connection_id,
    )


@router.post(
    "",
    operation_id="createConnection",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Connection created",
            "headers": {
                "Location": {
                    "description": "Relative URI of the created Connection.",
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
        status.HTTP_404_NOT_FOUND: {
            "model": ProblemDetail,
            "description": "Workspace or selected Project not found",
        },
        status.HTTP_409_CONFLICT: problem_openapi_response(
            ProblemCode.WORKSPACE_NOT_ACTIVE,
        ),
    },
    summary="Create connection",
)
async def create_connection(
    workspace_id: UUID,
    payload: CreateConnectionRequest,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionResponse:
    context = require_request_context(request)
    connection = await _connection_service(request).create_connection(
        user_id=principal.user_id,
        auth_session_id=principal.auth_session_id,
        workspace_id=workspace_id,
        name=payload.name,
        provider_key=payload.provider_key,
        access_policy=payload.access.to_domain(),
        request_id=context.request_id,
        trace_id=context.trace_id,
    )
    response.headers["Location"] = (
        f"/v1/workspaces/{workspace_id}/connections/{connection.connection_id}"
    )
    response.headers["Cache-Control"] = "no-store"
    return _connection_response(connection)


@router.get(
    "",
    operation_id="listConnections",
    response_model=ConnectionListResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
        status.HTTP_404_NOT_FOUND: problem_openapi_response(
            ProblemCode.WORKSPACE_NOT_FOUND,
        ),
    },
    summary="List connections",
)
async def list_connections(
    workspace_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
    limit: Annotated[int, Query(ge=1, le=MAX_CONNECTION_PAGE_LIMIT)] = (
        DEFAULT_CONNECTION_PAGE_LIMIT
    ),
    cursor: Annotated[str | None, Query(max_length=_MAX_CURSOR_LENGTH)] = None,
) -> ConnectionListResponse:
    page = await _connection_service(request).list_connections(
        user_id=principal.user_id,
        workspace_id=workspace_id,
        cursor=_decode_cursor(cursor),
        limit=limit,
    )
    response.headers["Cache-Control"] = "no-store"
    return ConnectionListResponse(
        items=[_connection_response(item) for item in page.items],
        next_cursor=_encode_cursor(page.next_cursor),
    )


async def _lifecycle_action(
    *,
    workspace_id: UUID,
    connection_id: UUID,
    action: ConnectionLifecycleAction,
    request: Request,
    response: Response,
    principal: AuthenticatedPrincipal,
) -> ConnectionResponse:
    context = require_request_context(request)
    connection = await _connection_service(request).transition_lifecycle(
        user_id=principal.user_id,
        auth_session_id=principal.auth_session_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        action=action,
        request_id=context.request_id,
        trace_id=context.trace_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _connection_response(connection)


_LIFECYCLE_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
        ProblemCode.AUTH_INVALID_CREDENTIALS,
    ),
    status.HTTP_403_FORBIDDEN: problem_openapi_response(
        ProblemCode.WORKSPACE_PERMISSION_DENIED,
    ),
    status.HTTP_404_NOT_FOUND: {
        "model": ProblemDetail,
        "description": "Workspace or Connection not found",
    },
    status.HTTP_409_CONFLICT: {
        "model": ProblemDetail,
        "description": "Workspace or Connection lifecycle conflict",
    },
}


@router.post(
    "/{connection_id}:disable",
    operation_id="disableConnection",
    response_model=ConnectionResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="Disable connection",
)
async def disable_connection(
    workspace_id: UUID,
    connection_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionResponse:
    return await _lifecycle_action(
        workspace_id=workspace_id,
        connection_id=connection_id,
        action=ConnectionLifecycleAction.DISABLE,
        request=request,
        response=response,
        principal=principal,
    )


@router.post(
    "/{connection_id}:enable",
    operation_id="enableConnection",
    response_model=ConnectionResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="Enable connection",
)
async def enable_connection(
    workspace_id: UUID,
    connection_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionResponse:
    return await _lifecycle_action(
        workspace_id=workspace_id,
        connection_id=connection_id,
        action=ConnectionLifecycleAction.ENABLE,
        request=request,
        response=response,
        principal=principal,
    )


@router.post(
    "/{connection_id}:archive",
    operation_id="archiveConnection",
    response_model=ConnectionResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="Archive connection",
)
async def archive_connection(
    workspace_id: UUID,
    connection_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionResponse:
    return await _lifecycle_action(
        workspace_id=workspace_id,
        connection_id=connection_id,
        action=ConnectionLifecycleAction.ARCHIVE,
        request=request,
        response=response,
        principal=principal,
    )


@router.get(
    "/{connection_id}",
    operation_id="getConnection",
    response_model=ConnectionResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: problem_openapi_response(
            ProblemCode.AUTH_INVALID_CREDENTIALS,
        ),
        status.HTTP_404_NOT_FOUND: {
            "model": ProblemDetail,
            "description": "Workspace or Connection not found",
        },
    },
    summary="Get connection",
)
async def get_connection(
    workspace_id: UUID,
    connection_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionResponse:
    connection = await _connection_service(request).get_connection(
        user_id=principal.user_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _connection_response(connection)


@router.patch(
    "/{connection_id}",
    operation_id="renameConnection",
    response_model=ConnectionResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="Rename connection",
)
async def rename_connection(
    workspace_id: UUID,
    connection_id: UUID,
    payload: RenameConnectionRequest,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionResponse:
    context = require_request_context(request)
    connection = await _connection_service(request).rename_connection(
        user_id=principal.user_id,
        auth_session_id=principal.auth_session_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        name=payload.name,
        request_id=context.request_id,
        trace_id=context.trace_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _connection_response(connection)


@router.get(
    "/{connection_id}/draft",
    operation_id="getConnectionDraft",
    response_model=ConnectionDraftResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="Get connection draft",
)
async def get_connection_draft(
    workspace_id: UUID,
    connection_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionDraftResponse:
    draft = await _connection_service(request).get_draft(
        user_id=principal.user_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _draft_response(draft)


@router.put(
    "/{connection_id}/draft",
    operation_id="putConnectionDraft",
    response_model=ConnectionDraftResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="Replace connection draft",
)
async def put_connection_draft(
    workspace_id: UUID,
    connection_id: UUID,
    payload: PutConnectionDraftRequest,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionDraftResponse:
    draft = await _connection_service(request).put_draft(
        user_id=principal.user_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        configuration=payload.configuration,
    )
    response.headers["Cache-Control"] = "no-store"
    return _draft_response(draft)


@router.get(
    "/{connection_id}/revisions",
    operation_id="listConnectionRevisions",
    response_model=ConnectionRevisionListResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="List connection revisions",
)
async def list_connection_revisions(
    workspace_id: UUID,
    connection_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
    before_revision: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_CONNECTION_REVISION_PAGE_LIMIT)] = (
        DEFAULT_CONNECTION_REVISION_PAGE_LIMIT
    ),
) -> ConnectionRevisionListResponse:
    revisions = await _connection_service(request).list_revisions(
        user_id=principal.user_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        before_revision=before_revision,
        limit=limit,
    )
    response.headers["Cache-Control"] = "no-store"
    return ConnectionRevisionListResponse(
        items=[_revision_metadata_response(item) for item in revisions.items],
        next_before_revision=revisions.next_before_revision,
    )


@router.post(
    "/{connection_id}/revisions",
    operation_id="publishConnectionRevision",
    response_model=ConnectionRevisionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_LIFECYCLE_RESPONSES,
    summary="Publish connection revision",
)
async def publish_connection_revision(
    workspace_id: UUID,
    connection_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionRevisionResponse:
    context = require_request_context(request)
    revision = await _connection_service(request).publish_revision(
        user_id=principal.user_id,
        auth_session_id=principal.auth_session_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        request_id=context.request_id,
        trace_id=context.trace_id,
    )
    response.headers["Location"] = (
        f"/v1/workspaces/{workspace_id}/connections/{connection_id}/revisions/"
        f"{revision.metadata.revision_id}"
    )
    response.headers["Cache-Control"] = "no-store"
    return _revision_response(revision)


@router.get(
    "/{connection_id}/revisions/{revision_id}",
    operation_id="getConnectionRevision",
    response_model=ConnectionRevisionResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="Get connection revision",
)
async def get_connection_revision(
    workspace_id: UUID,
    connection_id: UUID,
    revision_id: UUID,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionRevisionResponse:
    revision = await _connection_service(request).get_revision(
        user_id=principal.user_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        revision_id=revision_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _revision_response(revision)


@router.put(
    "/{connection_id}/access",
    operation_id="replaceConnectionAccess",
    response_model=ConnectionResponse,
    responses=_LIFECYCLE_RESPONSES,
    summary="Replace connection project access",
)
async def replace_connection_access(
    workspace_id: UUID,
    connection_id: UUID,
    payload: ConnectionAccessRequest,
    request: Request,
    response: Response,
    principal: Annotated[
        AuthenticatedPrincipal,
        Depends(require_authenticated_principal),
    ],
) -> ConnectionResponse:
    context = require_request_context(request)
    connection = await _connection_service(request).replace_access(
        user_id=principal.user_id,
        auth_session_id=principal.auth_session_id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        access_policy=payload.to_domain(),
        request_id=context.request_id,
        trace_id=context.trace_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return _connection_response(connection)
