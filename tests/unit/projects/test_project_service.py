from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from bff_control.domains.projects.contracts import (
    ProjectCreationAuthorizer,
    ProjectNotFoundError,
    ProjectPermissionDeniedError,
    ProjectRepository,
    ProjectWorkspaceNotActiveError,
    ProjectWorkspaceNotFoundError,
)
from bff_control.domains.projects.models import (
    Project,
    ProjectAuthorizationRole,
    ProjectLookup,
    ProjectPage,
    ProjectPageCursor,
    ProjectPageLookup,
    ProjectStatus,
    ProjectWorkspaceContext,
    ProjectWorkspaceStatus,
)
from bff_control.domains.projects.service import ProjectService


class FakeProjectRepository(ProjectRepository):
    def __init__(self) -> None:
        self.creation_context: ProjectWorkspaceContext | None = _context()
        self.created: dict[str, object] | None = None
        self.list_result = ProjectPageLookup(
            context=_context(),
            page=ProjectPage(items=(), next_cursor=None),
        )
        self.get_result = ProjectLookup(context=_context(), project=_project())

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
    ) -> Project:
        if self.creation_context is None:
            raise ProjectWorkspaceNotFoundError("workspace not found")
        authorize(self.creation_context)
        self.created = {
            "user_id": user_id,
            "auth_session_id": auth_session_id,
            "workspace_id": workspace_id,
            "name": name,
            "request_id": request_id,
            "trace_id": trace_id,
        }
        return _project(name=name)

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ProjectPageCursor | None,
        limit: int,
    ) -> ProjectPageLookup:
        del user_id, workspace_id, cursor, limit
        return self.list_result

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        project_id: UUID,
    ) -> ProjectLookup:
        del user_id, workspace_id, project_id
        return self.get_result


def _context(
    *,
    role: ProjectAuthorizationRole = ProjectAuthorizationRole.OWNER,
    status: ProjectWorkspaceStatus = ProjectWorkspaceStatus.ACTIVE,
) -> ProjectWorkspaceContext:
    return ProjectWorkspaceContext(
        workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
        role=role,
        status=status,
    )


def _project(*, name: str = "Project One") -> Project:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    return Project(
        project_id=UUID("00000000-0000-7000-8000-000000000902"),
        workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
        name=name,
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        archived_at=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        ProjectAuthorizationRole.OWNER,
        ProjectAuthorizationRole.ADMIN,
        ProjectAuthorizationRole.BUILDER,
    ],
)
async def test_create_project_normalizes_name_for_authorized_roles(
    role: ProjectAuthorizationRole,
) -> None:
    repository = FakeProjectRepository()
    repository.creation_context = _context(role=role)
    service = ProjectService(repository)

    result = await service.create_project(
        user_id=UUID("00000000-0000-7000-8000-000000000903"),
        auth_session_id=UUID("00000000-0000-7000-8000-000000000904"),
        workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
        name="  Project One  ",
        request_id=UUID("00000000-0000-7000-8000-000000000905"),
        trace_id="trace-project-create",
    )

    assert result.name == "Project One"
    assert repository.created is not None
    assert repository.created["name"] == "Project One"


@pytest.mark.asyncio
async def test_create_project_checks_permission_before_workspace_lifecycle() -> None:
    repository = FakeProjectRepository()
    repository.creation_context = _context(
        role=ProjectAuthorizationRole.VIEWER,
        status=ProjectWorkspaceStatus.SUSPENDED,
    )
    service = ProjectService(repository)

    with pytest.raises(ProjectPermissionDeniedError):
        await service.create_project(
            user_id=UUID("00000000-0000-7000-8000-000000000906"),
            auth_session_id=UUID("00000000-0000-7000-8000-000000000907"),
            workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
            name="Denied",
            request_id=UUID("00000000-0000-7000-8000-000000000908"),
            trace_id=None,
        )

    assert repository.created is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        ProjectWorkspaceStatus.SUSPENDED,
        ProjectWorkspaceStatus.ARCHIVED,
        ProjectWorkspaceStatus.PENDING_DELETION,
    ],
)
async def test_create_project_rejects_non_active_workspace(
    status: ProjectWorkspaceStatus,
) -> None:
    repository = FakeProjectRepository()
    repository.creation_context = _context(
        role=ProjectAuthorizationRole.BUILDER,
        status=status,
    )
    service = ProjectService(repository)

    with pytest.raises(ProjectWorkspaceNotActiveError):
        await service.create_project(
            user_id=UUID("00000000-0000-7000-8000-000000000909"),
            auth_session_id=UUID("00000000-0000-7000-8000-000000000910"),
            workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
            name="Blocked",
            request_id=UUID("00000000-0000-7000-8000-000000000911"),
            trace_id=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
async def test_create_project_rejects_invalid_name(name: str) -> None:
    repository = FakeProjectRepository()
    service = ProjectService(repository)

    with pytest.raises(ValueError):
        await service.create_project(
            user_id=UUID("00000000-0000-7000-8000-000000000912"),
            auth_session_id=UUID("00000000-0000-7000-8000-000000000913"),
            workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
            name=name,
            request_id=UUID("00000000-0000-7000-8000-000000000914"),
            trace_id=None,
        )

    assert repository.created is None


@pytest.mark.asyncio
async def test_list_projects_allows_viewer_and_preserves_page() -> None:
    repository = FakeProjectRepository()
    page = ProjectPage(
        items=(_project(),),
        next_cursor=ProjectPageCursor(
            created_at=_project().created_at,
            project_id=_project().project_id,
        ),
    )
    repository.list_result = ProjectPageLookup(
        context=_context(role=ProjectAuthorizationRole.VIEWER),
        page=page,
    )
    service = ProjectService(repository)

    result = await service.list_projects(
        user_id=UUID("00000000-0000-7000-8000-000000000915"),
        workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
        cursor=None,
        limit=50,
    )

    assert result == page


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_list_projects_enforces_page_limit(limit: int) -> None:
    repository = FakeProjectRepository()
    service = ProjectService(repository)

    with pytest.raises(ValueError):
        await service.list_projects(
            user_id=UUID("00000000-0000-7000-8000-000000000916"),
            workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
            cursor=None,
            limit=limit,
        )


@pytest.mark.asyncio
async def test_project_reads_hide_missing_workspace() -> None:
    repository = FakeProjectRepository()
    repository.list_result = ProjectPageLookup(
        context=None,
        page=ProjectPage(items=(), next_cursor=None),
    )
    repository.get_result = ProjectLookup(context=None, project=None)
    service = ProjectService(repository)

    with pytest.raises(ProjectWorkspaceNotFoundError):
        await service.list_projects(
            user_id=UUID("00000000-0000-7000-8000-000000000917"),
            workspace_id=UUID("00000000-0000-7000-8000-000000000918"),
            cursor=None,
            limit=50,
        )

    with pytest.raises(ProjectWorkspaceNotFoundError):
        await service.get_project(
            user_id=UUID("00000000-0000-7000-8000-000000000917"),
            workspace_id=UUID("00000000-0000-7000-8000-000000000918"),
            project_id=UUID("00000000-0000-7000-8000-000000000919"),
        )


@pytest.mark.asyncio
async def test_get_project_hides_missing_or_cross_workspace_project() -> None:
    repository = FakeProjectRepository()
    repository.get_result = ProjectLookup(context=_context(), project=None)
    service = ProjectService(repository)

    with pytest.raises(ProjectNotFoundError):
        await service.get_project(
            user_id=UUID("00000000-0000-7000-8000-000000000920"),
            workspace_id=UUID("00000000-0000-7000-8000-000000000901"),
            project_id=UUID("00000000-0000-7000-8000-000000000921"),
        )
