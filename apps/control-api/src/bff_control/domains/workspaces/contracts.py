"""Workspace domain interfaces."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from bff_control.domains.workspaces.models import WorkspaceAccess


class WorkspaceNotFoundError(Exception):
    """Raised when a Workspace is absent or deliberately hidden from the principal."""


class WorkspaceRepository(Protocol):
    """Persistence contract for Workspace authorization and bootstrap."""

    async def create_owned_workspace(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> WorkspaceAccess: ...

    async def list_for_user(self, user_id: UUID) -> tuple[WorkspaceAccess, ...]: ...

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
    ) -> WorkspaceAccess | None: ...


class WorkspaceManager(Protocol):
    """Application-facing Workspace operations."""

    async def create_workspace(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> WorkspaceAccess: ...

    async def list_workspaces(self, user_id: UUID) -> tuple[WorkspaceAccess, ...]: ...

    async def get_workspace(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
    ) -> WorkspaceAccess: ...
