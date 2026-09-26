from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from bff_control.core.settings import DatabaseSettings
from bff_control.domains.connections.contracts import (
    ConnectionConfigurationInvalidError,
    ConnectionNotFoundError,
    ConnectionPermissionDeniedError,
    ConnectionProjectNotFoundError,
    ConnectionWorkspaceNotFoundError,
)
from bff_control.domains.connections.models import (
    ConnectionAccessMode,
    ConnectionAccessPolicy,
    ConnectionLifecycleAction,
    ConnectionStatus,
)
from bff_control.domains.connections.providers import ConnectionProviderRegistry
from bff_control.domains.connections.service import ConnectionService
from bff_control.infrastructure.db.connection_repository import (
    SqlAlchemyConnectionRepository,
)
from bff_control.infrastructure.db.database import Database

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


def _service(database: Database) -> ConnectionService:
    return ConnectionService(
        SqlAlchemyConnectionRepository(database),
        ConnectionProviderRegistry.default(),
    )


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
    started_at = ended_at - timedelta(days=1) if ended_at is not None else datetime.now(tz=UTC)
    email = f"connection-{user_number}@example.test"
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
            VALUES (%s, 'Connection Workspace', %s)
            """,
            (workspace_id, workspace_status),
        )
        connection.execute(
            """
            INSERT INTO app.workspace_memberships (
                id, workspace_id, user_id, role, started_at, ended_at
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


def _seed_project(
    postgres_test_db: DatabaseTestEnvironment,
    *,
    workspace_id: UUID,
    project_number: int,
) -> UUID:
    project_id = UUID(_uuid(project_number))
    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.projects (id, workspace_id, name)
            VALUES (%s, %s, 'Connection Project')
            """,
            (project_id, workspace_id),
        )
    return project_id


async def test_connection_creation_commits_selected_access_and_audit(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2101,
        workspace_number=2102,
        membership_number=2103,
        role="BUILDER",
    )
    project_id = _seed_project(
        postgres_test_db,
        workspace_id=workspace_id,
        project_number=2104,
    )
    auth_session_id = UUID(_uuid(2105))
    request_id = UUID(_uuid(2106))
    database = _database(postgres_test_db)
    service = _service(database)

    try:
        created = await service.create_connection(
            user_id=user_id,
            auth_session_id=auth_session_id,
            workspace_id=workspace_id,
            name="  Primary API  ",
            provider_key="generic_http",
            access_policy=ConnectionAccessPolicy(
                mode=ConnectionAccessMode.SELECTED_PROJECTS,
                project_ids=(project_id,),
            ),
            request_id=request_id,
            trace_id="trace-connection-create",
        )
    finally:
        await database.dispose()

    assert created.name == "Primary API"
    assert created.status is ConnectionStatus.DRAFT
    assert created.access_policy.project_ids == (project_id,)

    with postgres_test_db.owner_connection() as connection:
        access = connection.execute(
            """
            SELECT workspace_id, project_id, granted_by_user_id
            FROM app.connection_project_access
            WHERE connection_id = %s
            """,
            (created.connection_id,),
        ).fetchone()
        audit = connection.execute(
            """
            SELECT actor_user_id, actor_role_snapshot, action, after_json,
                   request_id, trace_id, session_id
            FROM app.audit_events
            WHERE resource_id = %s AND action = 'CONNECTION_CREATED'
            """,
            (created.connection_id,),
        ).fetchone()

    assert access == (workspace_id, project_id, user_id)
    assert audit is not None
    assert audit[0:3] == (user_id, "BUILDER", "CONNECTION_CREATED")
    audit_after = cast(dict[str, object], audit[3])
    assert audit_after["provider_key"] == "generic_http"
    assert audit[4:7] == (
        str(request_id),
        "trace-connection-create",
        str(auth_session_id),
    )


async def test_builder_workspace_access_denial_rolls_back_all_writes(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2111,
        workspace_number=2112,
        membership_number=2113,
        role="BUILDER",
    )
    database = _database(postgres_test_db)
    service = _service(database)
    try:
        with pytest.raises(ConnectionPermissionDeniedError):
            await service.create_connection(
                user_id=user_id,
                auth_session_id=UUID(_uuid(2114)),
                workspace_id=workspace_id,
                name="Denied",
                provider_key="generic_http",
                access_policy=ConnectionAccessPolicy(
                    mode=ConnectionAccessMode.WORKSPACE,
                    project_ids=(),
                ),
                request_id=UUID(_uuid(2115)),
                trace_id=None,
            )
    finally:
        await database.dispose()

    with postgres_test_db.owner_connection() as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM app.connections WHERE workspace_id = %s),
                (SELECT count(*) FROM app.audit_events WHERE workspace_id = %s)
            """,
            (workspace_id, workspace_id),
        ).fetchone()
    assert counts == (0, 0)


async def test_cross_workspace_selected_project_is_hidden_and_atomic(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2121,
        workspace_number=2122,
        membership_number=2123,
        role="OWNER",
    )
    _, other_workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2124,
        workspace_number=2125,
        membership_number=2126,
        role="OWNER",
    )
    other_project_id = _seed_project(
        postgres_test_db,
        workspace_id=other_workspace_id,
        project_number=2127,
    )
    database = _database(postgres_test_db)
    service = _service(database)
    try:
        with pytest.raises(ConnectionProjectNotFoundError):
            await service.create_connection(
                user_id=user_id,
                auth_session_id=UUID(_uuid(2128)),
                workspace_id=workspace_id,
                name="Cross Workspace",
                provider_key="generic_http",
                access_policy=ConnectionAccessPolicy(
                    mode=ConnectionAccessMode.SELECTED_PROJECTS,
                    project_ids=(other_project_id,),
                ),
                request_id=UUID(_uuid(2129)),
                trace_id=None,
            )
    finally:
        await database.dispose()

    with postgres_test_db.owner_connection() as connection:
        count = connection.execute(
            "SELECT count(*) FROM app.connections WHERE workspace_id = %s",
            (workspace_id,),
        ).fetchone()
    assert count == (0,)


async def test_connection_list_is_stable_and_ended_membership_is_hidden(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2131,
        workspace_number=2132,
        membership_number=2133,
        role="VIEWER",
    )
    created_at = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
    connection_ids = [UUID(_uuid(value)) for value in (2134, 2135, 2136)]
    with postgres_test_db.owner_connection() as connection:
        for connection_id in connection_ids:
            connection.execute(
                """
                INSERT INTO app.connections (
                    id, workspace_id, name, provider_key, access_mode, created_at
                ) VALUES (%s, %s, %s, 'generic_http', 'WORKSPACE', %s)
                """,
                (connection_id, workspace_id, str(connection_id), created_at),
            )

    database = _database(postgres_test_db)
    service = _service(database)
    try:
        first = await service.list_connections(
            user_id=user_id,
            workspace_id=workspace_id,
            cursor=None,
            limit=2,
        )
        second = await service.list_connections(
            user_id=user_id,
            workspace_id=workspace_id,
            cursor=first.next_cursor,
            limit=2,
        )
    finally:
        await database.dispose()

    assert [item.connection_id for item in first.items] == sorted(
        connection_ids,
        reverse=True,
    )[:2]
    assert [item.connection_id for item in second.items] == [min(connection_ids)]

    ended_user_id, ended_workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2137,
        workspace_number=2138,
        membership_number=2139,
        role="VIEWER",
        ended_at=datetime.now(tz=UTC) - timedelta(minutes=1),
    )
    ended_database = _database(postgres_test_db)
    ended_service = _service(ended_database)
    try:
        with pytest.raises(ConnectionWorkspaceNotFoundError):
            await ended_service.list_connections(
                user_id=ended_user_id,
                workspace_id=ended_workspace_id,
                cursor=None,
                limit=50,
            )
    finally:
        await ended_database.dispose()


async def test_draft_publication_is_immutable_and_activates_connection(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2141,
        workspace_number=2142,
        membership_number=2143,
        role="BUILDER",
    )
    database = _database(postgres_test_db)
    service = _service(database)
    try:
        created = await service.create_connection(
            user_id=user_id,
            auth_session_id=UUID(_uuid(2144)),
            workspace_id=workspace_id,
            name="Publish Me",
            provider_key="generic_http",
            access_policy=ConnectionAccessPolicy(
                mode=ConnectionAccessMode.SELECTED_PROJECTS,
                project_ids=(),
            ),
            request_id=UUID(_uuid(2145)),
            trace_id=None,
        )
        with pytest.raises(ConnectionConfigurationInvalidError):
            await service.put_draft(
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=created.connection_id,
                configuration={
                    "base_url": "https://api.example.com",
                    "api_key": "must-not-be-stored",
                },
            )
        await service.put_draft(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            configuration={"base_url": "HTTPS://API.Example.COM/v1/"},
        )
        revision = await service.publish_revision(
            user_id=user_id,
            auth_session_id=UUID(_uuid(2146)),
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            request_id=UUID(_uuid(2147)),
            trace_id=None,
        )
        await service.put_draft(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            configuration={"base_url": "https://api.example.com/v2"},
        )
        await service.publish_revision(
            user_id=user_id,
            auth_session_id=UUID(_uuid(2148)),
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            request_id=UUID(_uuid(2149)),
            trace_id=None,
        )
        await service.put_draft(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            configuration={"base_url": "https://api.example.com/v3"},
        )
        await service.publish_revision(
            user_id=user_id,
            auth_session_id=UUID(_uuid(2190)),
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            request_id=UUID(_uuid(2191)),
            trace_id=None,
        )
        revision_page = await service.list_revisions(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            before_revision=None,
            limit=2,
        )
        final_page = await service.list_revisions(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            before_revision=revision_page.next_before_revision,
            limit=2,
        )
        activated = await service.get_connection(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=created.connection_id,
        )
    finally:
        await database.dispose()

    assert revision.metadata.revision_number == 1
    assert revision.configuration == {"base_url": "https://api.example.com/v1"}
    assert [item.revision_number for item in revision_page.items] == [3, 2]
    assert revision_page.next_before_revision == 2
    assert [item.revision_number for item in final_page.items] == [1]
    assert final_page.next_before_revision is None
    assert activated.status is ConnectionStatus.ACTIVE

    with postgres_test_db.owner_connection() as connection:
        audit = connection.execute(
            """
            SELECT after_json
            FROM app.audit_events
            WHERE resource_id = %s
              AND action = 'CONNECTION_REVISION_PUBLISHED'
            """,
            (created.connection_id,),
        ).fetchone()
    assert audit is not None
    audit_after = cast(dict[str, object], audit[0])
    assert audit_after["revision_number"] == 1
    assert "base_url" not in audit_after


async def test_builder_selected_access_and_owner_workspace_access_are_distinct(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2151,
        workspace_number=2152,
        membership_number=2153,
        role="BUILDER",
    )
    project_id = _seed_project(
        postgres_test_db,
        workspace_id=workspace_id,
        project_number=2154,
    )
    owner_id = UUID(_uuid(2155))
    with postgres_test_db.owner_connection() as connection:
        owner_email = "connection-2155@example.test"
        connection.execute(
            """
            INSERT INTO app.users (id, email, email_normalized)
            VALUES (%s, %s, %s)
            """,
            (owner_id, owner_email, owner_email),
        )
        connection.execute(
            """
            INSERT INTO app.workspace_memberships (
                id, workspace_id, user_id, role
            ) VALUES (%s, %s, %s, 'OWNER')
            """,
            (UUID(_uuid(2156)), workspace_id, owner_id),
        )

    database = _database(postgres_test_db)
    service = _service(database)
    try:
        created = await service.create_connection(
            user_id=user_id,
            auth_session_id=UUID(_uuid(2157)),
            workspace_id=workspace_id,
            name="Access Split",
            provider_key="generic_http",
            access_policy=ConnectionAccessPolicy(
                mode=ConnectionAccessMode.SELECTED_PROJECTS,
                project_ids=(),
            ),
            request_id=UUID(_uuid(2158)),
            trace_id=None,
        )
        selected = await service.replace_access(
            user_id=user_id,
            auth_session_id=UUID(_uuid(2159)),
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            access_policy=ConnectionAccessPolicy(
                mode=ConnectionAccessMode.SELECTED_PROJECTS,
                project_ids=(project_id,),
            ),
            request_id=UUID(_uuid(2160)),
            trace_id=None,
        )
        with pytest.raises(ConnectionPermissionDeniedError):
            await service.replace_access(
                user_id=user_id,
                auth_session_id=UUID(_uuid(2161)),
                workspace_id=workspace_id,
                connection_id=created.connection_id,
                access_policy=ConnectionAccessPolicy(
                    mode=ConnectionAccessMode.WORKSPACE,
                    project_ids=(),
                ),
                request_id=UUID(_uuid(2162)),
                trace_id=None,
            )
        workspace_wide = await service.replace_access(
            user_id=owner_id,
            auth_session_id=UUID(_uuid(2163)),
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            access_policy=ConnectionAccessPolicy(
                mode=ConnectionAccessMode.WORKSPACE,
                project_ids=(),
            ),
            request_id=UUID(_uuid(2164)),
            trace_id=None,
        )
    finally:
        await database.dispose()

    assert selected.access_policy.project_ids == (project_id,)
    assert workspace_wide.access_policy.mode is ConnectionAccessMode.WORKSPACE
    assert workspace_wide.access_policy.project_ids == ()


async def test_lifecycle_authorization_and_cross_workspace_existence_hiding(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    owner_id, workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2171,
        workspace_number=2172,
        membership_number=2173,
        role="OWNER",
    )
    builder_id = UUID(_uuid(2174))
    with postgres_test_db.owner_connection() as connection:
        builder_email = "connection-2174@example.test"
        connection.execute(
            "INSERT INTO app.users (id, email, email_normalized) VALUES (%s, %s, %s)",
            (builder_id, builder_email, builder_email),
        )
        connection.execute(
            """
            INSERT INTO app.workspace_memberships (id, workspace_id, user_id, role)
            VALUES (%s, %s, %s, 'BUILDER')
            """,
            (UUID(_uuid(2175)), workspace_id, builder_id),
        )
    database = _database(postgres_test_db)
    service = _service(database)
    try:
        created = await service.create_connection(
            user_id=owner_id,
            auth_session_id=UUID(_uuid(2176)),
            workspace_id=workspace_id,
            name="Lifecycle",
            provider_key="generic_http",
            access_policy=ConnectionAccessPolicy(
                mode=ConnectionAccessMode.WORKSPACE,
                project_ids=(),
            ),
            request_id=UUID(_uuid(2177)),
            trace_id=None,
        )
        await service.put_draft(
            user_id=owner_id,
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            configuration={"base_url": "https://api.example.com"},
        )
        await service.publish_revision(
            user_id=owner_id,
            auth_session_id=UUID(_uuid(2178)),
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            request_id=UUID(_uuid(2179)),
            trace_id=None,
        )
        with pytest.raises(ConnectionPermissionDeniedError):
            await service.transition_lifecycle(
                user_id=builder_id,
                auth_session_id=UUID(_uuid(2180)),
                workspace_id=workspace_id,
                connection_id=created.connection_id,
                action=ConnectionLifecycleAction.DISABLE,
                request_id=UUID(_uuid(2181)),
                trace_id=None,
            )
        disabled = await service.transition_lifecycle(
            user_id=owner_id,
            auth_session_id=UUID(_uuid(2182)),
            workspace_id=workspace_id,
            connection_id=created.connection_id,
            action=ConnectionLifecycleAction.DISABLE,
            request_id=UUID(_uuid(2183)),
            trace_id=None,
        )
    finally:
        await database.dispose()

    assert disabled.status is ConnectionStatus.DISABLED

    _, other_workspace_id = _seed_workspace_member(
        postgres_test_db,
        user_number=2184,
        workspace_number=2185,
        membership_number=2186,
        role="OWNER",
    )
    other_database = _database(postgres_test_db)
    other_service = _service(other_database)
    try:
        with pytest.raises(ConnectionNotFoundError):
            await other_service.get_connection(
                user_id=UUID(_uuid(2184)),
                workspace_id=other_workspace_id,
                connection_id=created.connection_id,
            )
    finally:
        await other_database.dispose()
