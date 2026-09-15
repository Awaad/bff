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
