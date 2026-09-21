"""Project application service."""

from __future__ import annotations

from uuid import UUID

from bff_control.domains.projects.contracts import (
    ProjectNotFoundError,
    ProjectPermissionDeniedError,
    ProjectRepository,
    ProjectWorkspaceNotActiveError,
    ProjectWorkspaceNotFoundError,
)
from bff_control.domains.projects.models import (
    Project,
    ProjectPage,
    ProjectPageCursor,
    ProjectWorkspaceContext,
)
from bff_control.domains.projects.policies import (
    can_create_project,
    can_read_projects,
    normalize_project_name,
    validate_project_page_limit,
    workspace_allows_project_creation,
)


class ProjectService:
    """Enforce Project authorization, lifecycle, and input policy."""

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    async def create_project(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> Project:
        normalized_name = normalize_project_name(name)
        return await self._repository.create_project(
            user_id=user_id,
            auth_session_id=auth_session_id,
            workspace_id=workspace_id,
            name=normalized_name,
            request_id=request_id,
            trace_id=trace_id,
            authorize=self._authorize_creation,
        )

    async def list_projects(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ProjectPageCursor | None,
        limit: int,
    ) -> ProjectPage:
        validated_limit = validate_project_page_limit(limit)
        lookup = await self._repository.list_for_user(
            user_id=user_id,
            workspace_id=workspace_id,
            cursor=cursor,
            limit=validated_limit,
        )
        self._authorize_read(lookup.context)
        return lookup.page

    async def get_project(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        project_id: UUID,
    ) -> Project:
        lookup = await self._repository.get_for_user(
            user_id=user_id,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        self._authorize_read(lookup.context)
        if lookup.project is None:
            raise ProjectNotFoundError("project not found")
        return lookup.project

    @staticmethod
    def _authorize_read(context: ProjectWorkspaceContext | None) -> None:
        if context is None or not can_read_projects(context.role):
            raise ProjectWorkspaceNotFoundError("workspace not found")

    @staticmethod
    def _authorize_creation(context: ProjectWorkspaceContext) -> None:
        if not can_create_project(context.role):
            raise ProjectPermissionDeniedError("project creation is not permitted")
        if not workspace_allows_project_creation(context.status):
            raise ProjectWorkspaceNotActiveError(
                "workspace lifecycle does not allow project creation",
            )
