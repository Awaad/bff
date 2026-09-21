"""Project domain interfaces."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from bff_control.domains.projects.models import (
    Project,
    ProjectLookup,
    ProjectPage,
    ProjectPageCursor,
    ProjectPageLookup,
    ProjectWorkspaceContext,
)


class ProjectWorkspaceNotFoundError(Exception):
    """Raised when the parent Workspace is absent or hidden from the principal."""


class ProjectNotFoundError(Exception):
    """Raised when a Project is absent or outside the authorized Workspace."""


class ProjectPermissionDeniedError(Exception):
    """Raised when the active Workspace role lacks a Project permission."""


class ProjectWorkspaceNotActiveError(Exception):
    """Raised when Workspace lifecycle blocks Project creation."""


ProjectCreationAuthorizer = Callable[[ProjectWorkspaceContext], None]


class ProjectRepository(Protocol):
    """Persistence contract for Project authorization and creation."""

    async def create_project(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
        authorize: ProjectCreationAuthorizer,
    ) -> Project: ...

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ProjectPageCursor | None,
        limit: int,
    ) -> ProjectPageLookup: ...

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        project_id: UUID,
    ) -> ProjectLookup: ...


class ProjectManager(Protocol):
    """Application-facing Project operations."""

    async def create_project(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> Project: ...

    async def list_projects(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ProjectPageCursor | None,
        limit: int,
    ) -> ProjectPage: ...

    async def get_project(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        project_id: UUID,
    ) -> Project: ...
