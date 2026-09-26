from __future__ import annotations

import psycopg
import pytest

from tests.support.database import IDS, DatabaseTestEnvironment


def test_role_bootstrap_grants_complete_expected_surface(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.owner_connection() as connection:
        row = connection.execute(
            """
            SELECT
                has_table_privilege(
                    'bff_runtime_writer',
                    'app.binding_revisions',
                    'SELECT'
                ),
                has_table_privilege(
                    'bff_runtime_writer',
                    'app.credential_secret_versions',
                    'SELECT'
                ),
                has_table_privilege(
                    'bff_runtime_writer',
                    'app.executions',
                    'INSERT'
                ),
                has_table_privilege(
                    'bff_runtime_writer',
                    'app.usage_events',
                    'INSERT'
                ),
                has_table_privilege(
                    'bff_runtime_writer',
                    'app.outbox_events',
                    'INSERT'
                ),
                has_table_privilege(
                    'bff_retention',
                    'app.idempotency_records',
                    'DELETE'
                ),
                has_table_privilege(
                    'bff_retention',
                    'app.outbox_events',
                    'DELETE'
                ),
                has_table_privilege(
                    'bff_worker_writer',
                    'app.bindings',
                    'UPDATE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.bindings',
                    'status',
                    'UPDATE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.bindings',
                    'exposure_mode',
                    'UPDATE'
                )
            """,
        ).fetchone()

    assert row == (
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        True,
        False,
    )


@pytest.mark.parametrize("column", ["kind", "exposure_mode", "status"])
def test_worker_cannot_update_bindings(
    postgres_test_db: DatabaseTestEnvironment,
    column: str,
) -> None:
    values = {
        "kind": "QUERY",
        "exposure_mode": "PUBLIC",
        "status": "DISABLED",
    }

    with (
        postgres_test_db.role_connection("worker") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            f"UPDATE app.bindings SET {column} = %s WHERE id = %s",
            (values[column], IDS["binding_acl"]),
        )


def test_control_can_update_binding_lifecycle_column(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.role_connection("control") as connection:
        connection.execute(
            """
            UPDATE app.bindings
            SET status = 'DISABLED'
            WHERE id = %s
            """,
            (IDS["binding_acl"],),
        )

        row = connection.execute(
            "SELECT status FROM app.bindings WHERE id = %s",
            (IDS["binding_acl"],),
        ).fetchone()

    assert row == ("DISABLED",)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("kind", "QUERY"),
        ("exposure_mode", "PUBLIC"),
    ],
)
def test_control_cannot_mutate_binding_identity(
    postgres_test_db: DatabaseTestEnvironment,
    column: str,
    value: str,
) -> None:
    with (
        postgres_test_db.role_connection("control") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            f"UPDATE app.bindings SET {column} = %s WHERE id = %s",
            (value, IDS["binding_acl"]),
        )


@pytest.mark.parametrize("column", ["workspace_id", "provider_key"])
def test_control_cannot_mutate_connection_identity(
    postgres_test_db: DatabaseTestEnvironment,
    column: str,
) -> None:
    values = {
        "workspace_id": IDS["workspace_2"],
        "provider_key": "changed-provider",
    }

    with (
        postgres_test_db.role_connection("control") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            f"UPDATE app.connections SET {column} = %s WHERE id = %s",
            (values[column], IDS["connection_1"]),
        )


def test_control_can_update_connection_mutable_columns(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.role_connection("control") as connection:
        connection.execute(
            """
            UPDATE app.connections
            SET name = 'Renamed Connection', access_mode = 'SELECTED_PROJECTS'
            WHERE id = %s
            """,
            (IDS["connection_1"],),
        )
        row = connection.execute(
            "SELECT name, access_mode FROM app.connections WHERE id = %s",
            (IDS["connection_1"],),
        ).fetchone()

    assert row == ("Renamed Connection", "SELECTED_PROJECTS")


def test_control_can_delete_connection_project_access(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.role_connection("control") as connection:
        connection.execute(
            """
            INSERT INTO app.connection_project_access (
                workspace_id, connection_id, project_id
            ) VALUES (%s, %s, %s)
            """,
            (IDS["workspace_1"], IDS["connection_1"], IDS["project_1"]),
        )
        connection.execute(
            """
            DELETE FROM app.connection_project_access
            WHERE connection_id = %s AND project_id = %s
            """,
            (IDS["connection_1"], IDS["project_1"]),
        )


def test_worker_cannot_author_connection_state(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with (
        postgres_test_db.role_connection("worker") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            """
            UPDATE app.connections
            SET name = 'Worker Mutation'
            WHERE id = %s
            """,
            (IDS["connection_1"],),
        )


def test_runtime_can_update_execution_attempt_lifecycle(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.role_connection("runtime") as connection:
        connection.execute(
            """
            UPDATE app.execution_attempts
            SET status = 'FAILED', error_code = 'fixture_failure'
            WHERE id = %s
            """,
            (IDS["execution_attempt_acl"],),
        )

        row = connection.execute(
            """
            SELECT status, error_code
            FROM app.execution_attempts
            WHERE id = %s
            """,
            (IDS["execution_attempt_acl"],),
        ).fetchone()

    assert row == ("FAILED", "fixture_failure")


def test_runtime_cannot_mutate_execution_attempt_identity(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with (
        postgres_test_db.role_connection("runtime") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            """
            UPDATE app.execution_attempts
            SET attempt_number = 2
            WHERE id = %s
            """,
            (IDS["execution_attempt_acl"],),
        )
