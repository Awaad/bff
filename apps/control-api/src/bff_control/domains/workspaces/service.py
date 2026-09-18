"""Workspace application service."""

from __future__ import annotations

from uuid import UUID

from bff_control.domains.workspaces.contracts import (
    WorkspaceNotFoundError,
    WorkspaceRepository,
)
from bff_control.domains.workspaces.models import WorkspaceAccess
from bff_control.domains.workspaces.policies import (
    can_read_workspace,
    normalize_workspace_name,
)


class WorkspaceService:
    """Enforce Workspace bootstrap and membership authorization policy."""

    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    async def create_workspace(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> WorkspaceAccess:
        normalized_name = normalize_workspace_name(name)
        return await self._repository.create_owned_workspace(
            user_id=user_id,
            auth_session_id=auth_session_id,
            name=normalized_name,
            request_id=request_id,
            trace_id=trace_id,
        )

    async def list_workspaces(self, user_id: UUID) -> tuple[WorkspaceAccess, ...]:
        accesses = await self._repository.list_for_user(user_id)
        return tuple(access for access in accesses if can_read_workspace(access.role))

    async def get_workspace(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
    ) -> WorkspaceAccess:
        access = await self._repository.get_for_user(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if access is None or not can_read_workspace(access.role):
            raise WorkspaceNotFoundError("workspace not found")
        return access
