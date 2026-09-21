"""Project domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"
    PENDING_DELETION = "PENDING_DELETION"


class ProjectAuthorizationRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    BUILDER = "BUILDER"
    VIEWER = "VIEWER"


class ProjectWorkspaceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"
    PENDING_DELETION = "PENDING_DELETION"


@dataclass(frozen=True, slots=True)
class ProjectWorkspaceContext:
    """Workspace state used by Project authorization policy."""

    workspace_id: UUID
    status: ProjectWorkspaceStatus
    role: ProjectAuthorizationRole


@dataclass(frozen=True, slots=True)
class Project:
    project_id: UUID
    workspace_id: UUID
    name: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProjectPageCursor:
    created_at: datetime
    project_id: UUID


@dataclass(frozen=True, slots=True)
class ProjectPage:
    items: tuple[Project, ...]
    next_cursor: ProjectPageCursor | None


@dataclass(frozen=True, slots=True)
class ProjectPageLookup:
    context: ProjectWorkspaceContext | None
    page: ProjectPage


@dataclass(frozen=True, slots=True)
class ProjectLookup:
    context: ProjectWorkspaceContext | None
    project: Project | None
