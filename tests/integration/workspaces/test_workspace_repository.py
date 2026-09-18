from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from bff_control.core.settings import DatabaseSettings
from bff_control.domains.workspaces.models import WorkspaceRole, WorkspaceStatus
from bff_control.infrastructure.db.database import Database
from bff_control.infrastructure.db.workspace_repository import SqlAlchemyWorkspaceRepository

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


def _seed_user(
    postgres_test_db: DatabaseTestEnvironment,
    *,
    number: int,
) -> UUID:
    user_id = _uuid(number)
    email = f"workspace-{number}@example.test"
    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.users (
                id,
                email,
                email_normalized,
                display_name
            ) VALUES (%s, %s, %s, 'Workspace User')
            """,
            (user_id, email, email),
        )
    return UUID(user_id)


async def test_create_owned_workspace_commits_owner_membership_and_audit(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id = _seed_user(postgres_test_db, number=801)
    auth_session_id = UUID(_uuid(802))
    request_id = UUID(_uuid(803))
    database = _database(postgres_test_db)
    repository = SqlAlchemyWorkspaceRepository(database)

    try:
        access = await repository.create_owned_workspace(
            user_id=user_id,
            auth_session_id=auth_session_id,
            name="Production Workspace",
            request_id=request_id,
            trace_id="trace-workspace-create",
        )
    finally:
        await database.dispose()

    assert access.status is WorkspaceStatus.ACTIVE
    assert access.role is WorkspaceRole.OWNER
    assert access.name == "Production Workspace"

    with postgres_test_db.owner_connection() as connection:
        membership = connection.execute(
            """
            SELECT role, ended_at
            FROM app.workspace_memberships
            WHERE workspace_id = %s
              AND user_id = %s
            """,
            (access.workspace_id, user_id),
        ).fetchone()
        audit = connection.execute(
            """
            SELECT
                scope,
                actor_type,
                actor_user_id,
                actor_role_snapshot,
                effective_user_id,
                action,
                outcome,
                resource_type,
                resource_id,
                after_json,
                request_id,
                trace_id,
                session_id,
                surface
            FROM app.audit_events
            WHERE resource_id = %s
              AND action = 'WORKSPACE_CREATED'
            """,
            (access.workspace_id,),
        ).fetchone()

    assert membership == ("OWNER", None)
    assert audit is not None
    assert audit[0:9] == (
        "TENANT",
        "USER",
        user_id,
        "OWNER",
        user_id,
        "WORKSPACE_CREATED",
        "SUCCEEDED",
        "WORKSPACE",
        access.workspace_id,
    )
    assert audit[9] == {
        "name": "Production Workspace",
        "role": "OWNER",
        "status": "ACTIVE",
    }
    assert audit[10] == str(request_id)
    assert audit[11] == "trace-workspace-create"
    assert audit[12] == str(auth_session_id)
    assert audit[13] == "PUBLIC_API"


async def test_workspace_reads_require_current_membership_and_preserve_lifecycle(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id = _seed_user(postgres_test_db, number=811)
    other_user_id = _seed_user(postgres_test_db, number=812)
    active_workspace_id = UUID(_uuid(813))
    ended_workspace_id = UUID(_uuid(814))
    other_workspace_id = UUID(_uuid(815))
    now = datetime.now(tz=UTC)

    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.workspaces (id, name, status) VALUES
                (%s, 'Suspended Workspace', 'SUSPENDED'),
                (%s, 'Ended Membership Workspace', 'ACTIVE'),
                (%s, 'Other User Workspace', 'ACTIVE')
            """,
            (active_workspace_id, ended_workspace_id, other_workspace_id),
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
            ) VALUES
                (%s, %s, %s, 'VIEWER', %s, NULL),
                (%s, %s, %s, 'ADMIN', %s, %s),
                (%s, %s, %s, 'OWNER', %s, NULL)
            """,
            (
                UUID(_uuid(816)),
                active_workspace_id,
                user_id,
                now - timedelta(days=2),
                UUID(_uuid(817)),
                ended_workspace_id,
                user_id,
                now - timedelta(days=3),
                now - timedelta(days=1),
                UUID(_uuid(818)),
                other_workspace_id,
                other_user_id,
                now - timedelta(days=1),
            ),
        )

    database = _database(postgres_test_db)
    repository = SqlAlchemyWorkspaceRepository(database)

    try:
        visible = await repository.list_for_user(user_id)
        suspended = await repository.get_for_user(
            user_id=user_id,
            workspace_id=active_workspace_id,
        )
        ended = await repository.get_for_user(
            user_id=user_id,
            workspace_id=ended_workspace_id,
        )
        other = await repository.get_for_user(
            user_id=user_id,
            workspace_id=other_workspace_id,
        )
    finally:
        await database.dispose()

    assert len(visible) == 1
    assert visible[0].workspace_id == active_workspace_id
    assert visible[0].status is WorkspaceStatus.SUSPENDED
    assert visible[0].role is WorkspaceRole.VIEWER
    assert suspended is not None
    assert ended is None
    assert other is None
