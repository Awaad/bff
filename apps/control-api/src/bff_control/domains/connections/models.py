"""Connection domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

type JsonObject = dict[str, object]


class ConnectionStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    ARCHIVED = "ARCHIVED"


class ConnectionAccessMode(StrEnum):
    WORKSPACE = "WORKSPACE"
    SELECTED_PROJECTS = "SELECTED_PROJECTS"


class ConnectionAuthorizationRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    BUILDER = "BUILDER"
    VIEWER = "VIEWER"


class ConnectionWorkspaceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"
    PENDING_DELETION = "PENDING_DELETION"


class ConnectionLifecycleAction(StrEnum):
    DISABLE = "DISABLE"
    ENABLE = "ENABLE"
    ARCHIVE = "ARCHIVE"


@dataclass(frozen=True, slots=True)
class ConnectionWorkspaceContext:
    workspace_id: UUID
    status: ConnectionWorkspaceStatus
    role: ConnectionAuthorizationRole


@dataclass(frozen=True, slots=True)
class ConnectionMutationContext:
    workspace: ConnectionWorkspaceContext
    connection_id: UUID
    provider_key: str
    access_mode: ConnectionAccessMode
    status: ConnectionStatus


@dataclass(frozen=True, slots=True)
class ConnectionAccessPolicy:
    mode: ConnectionAccessMode
    project_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class Connection:
    connection_id: UUID
    workspace_id: UUID
    name: str
    provider_key: str
    access_policy: ConnectionAccessPolicy
    status: ConnectionStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConnectionDraft:
    connection_id: UUID
    workspace_id: UUID
    configuration: JsonObject
    updated_by_user_id: UUID | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PublishedConnectionConfiguration:
    definition_schema_version: int
    configuration: JsonObject
    config_hash: bytes


@dataclass(frozen=True, slots=True)
class ConnectionRevisionMetadata:
    revision_id: UUID
    connection_id: UUID
    workspace_id: UUID
    revision_number: int
    definition_schema_version: int
    config_hash_hex: str
    created_by_user_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConnectionRevision:
    metadata: ConnectionRevisionMetadata
    configuration: JsonObject


@dataclass(frozen=True, slots=True)
class ConnectionPageCursor:
    created_at: datetime
    connection_id: UUID


@dataclass(frozen=True, slots=True)
class ConnectionPage:
    items: tuple[Connection, ...]
    next_cursor: ConnectionPageCursor | None


@dataclass(frozen=True, slots=True)
class ConnectionPageLookup:
    context: ConnectionWorkspaceContext | None
    page: ConnectionPage


@dataclass(frozen=True, slots=True)
class ConnectionLookup:
    context: ConnectionWorkspaceContext | None
    connection: Connection | None


@dataclass(frozen=True, slots=True)
class ConnectionDraftLookup:
    context: ConnectionMutationContext | None
    draft: ConnectionDraft | None


@dataclass(frozen=True, slots=True)
class ConnectionRevisionPage:
    items: tuple[ConnectionRevisionMetadata, ...]
    next_before_revision: int | None


@dataclass(frozen=True, slots=True)
class ConnectionRevisionPageLookup:
    context: ConnectionMutationContext | None
    page: ConnectionRevisionPage


@dataclass(frozen=True, slots=True)
class ConnectionRevisionLookup:
    context: ConnectionMutationContext | None
    revision: ConnectionRevision | None
