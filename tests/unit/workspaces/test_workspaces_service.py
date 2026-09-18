from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from bff_control.domains.workspaces.contracts import (
    WorkspaceNotFoundError,
    WorkspaceRepository,
)
from bff_control.domains.workspaces.models import (
    WorkspaceAccess,
    WorkspaceRole,
    WorkspaceStatus,
)
from bff_control.domains.workspaces.service import WorkspaceService


class FakeWorkspaceRepository(WorkspaceRepository):
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.list_result: tuple[WorkspaceAccess, ...] = ()
        self.get_result: WorkspaceAccess | None = None

    async def create_owned_workspace(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> WorkspaceAccess:
        self.created = {
            "user_id": user_id,
            "auth_session_id": auth_session_id,
            "name": name,
            "request_id": request_id,
            "trace_id": trace_id,
        }
        return _access(role=WorkspaceRole.OWNER)

    async def list_for_user(self, user_id: UUID) -> tuple[WorkspaceAccess, ...]:
        del user_id
        return self.list_result

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
    ) -> WorkspaceAccess | None:
        del user_id, workspace_id
        return self.get_result


def _access(*, role: WorkspaceRole) -> WorkspaceAccess:
    now = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    return WorkspaceAccess(
        workspace_id=UUID("00000000-0000-7000-8000-000000000701"),
        name="Workspace One",
        status=WorkspaceStatus.ACTIVE,
        role=role,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_create_workspace_normalizes_name_and_forwards_audit_context() -> None:
    repository = FakeWorkspaceRepository()
    service = WorkspaceService(repository)
    user_id = UUID("00000000-0000-7000-8000-000000000702")
    auth_session_id = UUID("00000000-0000-7000-8000-000000000703")
    request_id = UUID("00000000-0000-7000-8000-000000000704")

    result = await service.create_workspace(
        user_id=user_id,
        auth_session_id=auth_session_id,
        name="  Workspace One  ",
        request_id=request_id,
        trace_id="trace-1",
    )

    assert result.role is WorkspaceRole.OWNER
    assert repository.created == {
        "user_id": user_id,
        "auth_session_id": auth_session_id,
        "name": "Workspace One",
        "request_id": request_id,
        "trace_id": "trace-1",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
async def test_create_workspace_rejects_invalid_name(name: str) -> None:
    repository = FakeWorkspaceRepository()
    service = WorkspaceService(repository)

    with pytest.raises(ValueError):
        await service.create_workspace(
            user_id=UUID("00000000-0000-7000-8000-000000000705"),
            auth_session_id=UUID("00000000-0000-7000-8000-000000000706"),
            name=name,
            request_id=UUID("00000000-0000-7000-8000-000000000707"),
            trace_id=None,
        )

    assert repository.created is None


@pytest.mark.asyncio
async def test_list_workspaces_returns_all_current_read_roles() -> None:
    repository = FakeWorkspaceRepository()
    repository.list_result = tuple(_access(role=role) for role in WorkspaceRole)
    service = WorkspaceService(repository)

    result = await service.list_workspaces(UUID("00000000-0000-7000-8000-000000000708"))

    assert [access.role for access in result] == list(WorkspaceRole)


@pytest.mark.asyncio
async def test_get_workspace_hides_absent_or_unauthorized_workspace() -> None:
    repository = FakeWorkspaceRepository()
    service = WorkspaceService(repository)

    with pytest.raises(WorkspaceNotFoundError):
        await service.get_workspace(
            user_id=UUID("00000000-0000-7000-8000-000000000709"),
            workspace_id=UUID("00000000-0000-7000-8000-000000000710"),
        )
