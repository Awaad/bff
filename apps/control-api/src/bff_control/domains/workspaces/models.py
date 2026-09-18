"""Workspace domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class WorkspaceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"
    PENDING_DELETION = "PENDING_DELETION"


class WorkspaceRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    BUILDER = "BUILDER"
    VIEWER = "VIEWER"


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    """One Workspace plus the principal's active membership role."""

    workspace_id: UUID
    name: str
    status: WorkspaceStatus
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime
