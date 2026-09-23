from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from bff_control.core.settings import DatabaseSettings
from bff_control.domains.projects.contracts import (
    ProjectNotFoundError,
    ProjectPermissionDeniedError,
    ProjectWorkspaceNotActiveError,
    ProjectWorkspaceNotFoundError,
)
from bff_control.domains.projects.models import ProjectStatus
from bff_control.domains.projects.service import ProjectService
from bff_control.infrastructure.db.database import Database
from bff_control.infrastructure.db.project_repository import SqlAlchemyProjectRepository

from tests.support.database import DatabaseTestEnvironment

pytestmark = [pytest.mark.postgres, pytest.mark.asyncio]


def _uuid(number: int) -> str:
    return f"00000000-0000-7000-8000-{number:012d}"


def _database(postgres_test_db: DatabaseTestEnvironment) -> Database:
    control_url = postgres_test_db.login_urls["control"]
    values: dict[str, object] = {
        "database_url": control_url.set(
            drivername="postgresql+asyncpg",
        ).render_as_string(hide_password=False),
        "migration_database_url": control_url.set(
            drivername="postgresql+psycopg",
        ).render_as_string(hide_password=False),
    }
    return Database(DatabaseSettings.model_validate(values))


def _seed_workspace_member(
    postgres_test_db: DatabaseTestEnvironment,
    *,
    user_number: int,
    workspace_number: int,
    membership_number: int,
    role: str,
    workspace_status: str = "ACTIVE",
    ended_at: datetime | None = None,
) -> tuple[UUID, UUID]:
    user_id = UUID(_uuid(user_number))
    workspace_id = UUID(_uuid(workspace_number))
    email = f"project-{user_number}@example.test"
    started_at = ended_at - timedelta(days=1) if ended_at is not None else datetime.now(tz=UTC)
    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.users (id, email, email_normalized)
            VALUES (%s, %s, %s)
            """,
            (user_id, email, email),
        )
        connection.execute(
            """
            INSERT INTO app.workspaces (id, name, status)
            VALUES (%s, 'Project Workspace', %s)
            """,
            (workspace_id, workspace_status),
        )
        connection.execute(
            """
            INSERT INTO app.workspace_memberships (
                id,
                workspace_id,
                user_id,
                role,
                started_at,
                ended_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                UUID(_uuid(membership_number)),
                workspace_id,
                user_id,
                role,
                started_at,
                ended_at,
            ),
        )
    return user_id, workspace_id


async def test_create_project_commits_locked_role_snapshot_and_audit(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=1001,
        workspace_number=1002,
        membership_number=1003,
        role="BUILDER",
    )
    auth_session_id = UUID(_uuid(1004))
    request_id = UUID(_uuid(1005))
    database = _database(postgres_test_db)
    service = ProjectService(SqlAlchemyProjectRepository(database))

    try:
        project = await service.create_project(
            user_id=user_id,
            auth_session_id=auth_session_id,
            workspace_id=workspace_id,
            name="  Production Project  ",
            request_id=request_id,
            trace_id="trace-project-create",
        )
    finally:
        await database.dispose()

    assert project.workspace_id == workspace_id
    assert project.name == "Production Project"
    assert project.status is ProjectStatus.ACTIVE

    with postgres_test_db.owner_connection() as connection:
        audit = connection.execute(
            """
            SELECT
                workspace_id,
                project_id,
                actor_user_id,
                actor_role_snapshot,
                action,
                outcome,
                resource_type,
                resource_id,
                after_json,
                request_id,
                trace_id,
                session_id
            FROM app.audit_events
            WHERE project_id = %s
              AND action = 'PROJECT_CREATED'
            """,
            (project.project_id,),
        ).fetchone()

    assert audit is not None
    assert audit[0:8] == (
        workspace_id,
        project.project_id,
        user_id,
        "BUILDER",
        "PROJECT_CREATED",
        "SUCCEEDED",
        "PROJECT",
        project.project_id,
    )
    assert audit[8] == {"name": "Production Project", "status": "ACTIVE"}
    assert audit[9] == str(request_id)
    assert audit[10] == "trace-project-create"
    assert audit[11] == str(auth_session_id)


@pytest.mark.parametrize(
    ("role", "workspace_status", "expected_error"),
    [
        ("VIEWER", "ACTIVE", ProjectPermissionDeniedError),
        ("VIEWER", "SUSPENDED", ProjectPermissionDeniedError),
        ("BUILDER", "SUSPENDED", ProjectWorkspaceNotActiveError),
        ("OWNER", "ARCHIVED", ProjectWorkspaceNotActiveError),
    ],
)
async def test_create_project_rolls_back_policy_denials(
    postgres_test_db: DatabaseTestEnvironment,
    role: str,
    workspace_status: str,
    expected_error: type[Exception],
) -> None:
    base = {
        ("VIEWER", "ACTIVE"): 1010,
        ("VIEWER", "SUSPENDED"): 1020,
        ("BUILDER", "SUSPENDED"): 1030,
        ("OWNER", "ARCHIVED"): 1040,
    }[(role, workspace_status)]
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=base + 1,
        workspace_number=base + 2,
        membership_number=base + 3,
        role=role,
        workspace_status=workspace_status,
    )
    database = _database(postgres_test_db)
    service = ProjectService(SqlAlchemyProjectRepository(database))

    try:
        with pytest.raises(expected_error):
            await service.create_project(
                user_id=user_id,
                auth_session_id=UUID(_uuid(base + 4)),
                workspace_id=workspace_id,
                name="Must Not Commit",
                request_id=UUID(_uuid(base + 5)),
                trace_id=None,
            )
    finally:
        await database.dispose()

    with postgres_test_db.owner_connection() as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM app.projects WHERE workspace_id = %s),
                (SELECT count(*) FROM app.audit_events WHERE workspace_id = %s)
            """,
            (workspace_id, workspace_id),
        ).fetchone()

    assert counts == (0, 0)


async def test_project_creation_hides_ended_membership(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=1051,
        workspace_number=1052,
        membership_number=1053,
        role="OWNER",
        ended_at=datetime.now(tz=UTC) - timedelta(minutes=1),
    )
    database = _database(postgres_test_db)
    service = ProjectService(SqlAlchemyProjectRepository(database))

    try:
        with pytest.raises(ProjectWorkspaceNotFoundError):
            await service.create_project(
                user_id=user_id,
                auth_session_id=UUID(_uuid(1054)),
                workspace_id=workspace_id,
                name="Hidden",
                request_id=UUID(_uuid(1055)),
                trace_id=None,
            )
    finally:
        await database.dispose()


async def test_project_list_is_bounded_and_uses_stable_descending_cursor(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=1061,
        workspace_number=1062,
        membership_number=1063,
        role="VIEWER",
        workspace_status="SUSPENDED",
    )
    created_at = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    project_ids = [UUID(_uuid(number)) for number in (1064, 1065, 1066)]
    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.projects (id, workspace_id, name, status, created_at)
            VALUES
                (%s, %s, 'Active Project', 'ACTIVE', %s),
                (%s, %s, 'Suspended Project', 'SUSPENDED', %s),
                (%s, %s, 'Archived Project', 'ARCHIVED', %s)
            """,
            (
                project_ids[0],
                workspace_id,
                created_at,
                project_ids[1],
                workspace_id,
                created_at,
                project_ids[2],
                workspace_id,
                created_at,
            ),
        )

    database = _database(postgres_test_db)
    service = ProjectService(SqlAlchemyProjectRepository(database))
    try:
        first = await service.list_projects(
            user_id=user_id,
            workspace_id=workspace_id,
            cursor=None,
            limit=2,
        )
        second = await service.list_projects(
            user_id=user_id,
            workspace_id=workspace_id,
            cursor=first.next_cursor,
            limit=2,
        )
    finally:
        await database.dispose()

    assert [item.project_id for item in first.items] == [project_ids[2], project_ids[1]]
    assert first.next_cursor is not None
    assert first.next_cursor.project_id == project_ids[1]
    assert [item.project_id for item in second.items] == [project_ids[0]]
    assert second.next_cursor is None
    assert {item.status for item in (*first.items, *second.items)} == {
        ProjectStatus.ACTIVE,
        ProjectStatus.SUSPENDED,
        ProjectStatus.ARCHIVED,
    }


async def test_empty_project_list_distinguishes_visible_from_ended_membership(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    visible_user_id, visible_workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=1081,
        workspace_number=1082,
        membership_number=1083,
        role="VIEWER",
    )
    ended_user_id, ended_workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=1084,
        workspace_number=1085,
        membership_number=1086,
        role="OWNER",
        ended_at=datetime.now(tz=UTC) - timedelta(minutes=1),
    )
    database = _database(postgres_test_db)
    service = ProjectService(SqlAlchemyProjectRepository(database))

    try:
        visible = await service.list_projects(
            user_id=visible_user_id,
            workspace_id=visible_workspace_id,
            cursor=None,
            limit=50,
        )
        with pytest.raises(ProjectWorkspaceNotFoundError):
            await service.list_projects(
                user_id=ended_user_id,
                workspace_id=ended_workspace_id,
                cursor=None,
                limit=50,
            )
    finally:
        await database.dispose()

    assert visible.items == ()
    assert visible.next_cursor is None


async def test_project_detail_hides_cross_workspace_identity(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=1071,
        workspace_number=1072,
        membership_number=1073,
        role="ADMIN",
    )
    other_workspace_id = UUID(_uuid(1074))
    other_project_id = UUID(_uuid(1075))
    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            "INSERT INTO app.workspaces (id, name) VALUES (%s, 'Other Workspace')",
            (other_workspace_id,),
        )
        connection.execute(
            """
            INSERT INTO app.projects (id, workspace_id, name)
            VALUES (%s, %s, 'Other Project')
            """,
            (other_project_id, other_workspace_id),
        )

    database = _database(postgres_test_db)
    service = ProjectService(SqlAlchemyProjectRepository(database))
    try:
        with pytest.raises(ProjectNotFoundError):
            await service.get_project(
                user_id=user_id,
                workspace_id=workspace_id,
                project_id=other_project_id,
            )
    finally:
        await database.dispose()
