from __future__ import annotations

import psycopg
import pytest

from tests.support.database import DatabaseTestEnvironment

USER_ID = "00000000-0000-7000-8000-000000000221"
IDENTITY_ID = "00000000-0000-7000-8000-000000000222"


def _seed_identity(postgres_test_db: DatabaseTestEnvironment) -> None:
    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.users (
                id,
                email,
                email_normalized
            ) VALUES (
                %s,
                'acl-identity@example.test',
                'acl-identity@example.test'
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (USER_ID,),
        )
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (
                id,
                user_id,
                issuer,
                subject
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (IDENTITY_ID, USER_ID, "https://issuer.example", "subject-acl"),
        )


def test_auth_identity_role_surface_is_least_privilege(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.owner_connection() as connection:
        row = connection.execute(
            """
            SELECT
                has_table_privilege(
                    'bff_control_writer',
                    'app.user_auth_identities',
                    'SELECT'
                ),
                has_table_privilege(
                    'bff_control_writer',
                    'app.user_auth_identities',
                    'INSERT'
                ),
                has_table_privilege(
                    'bff_control_writer',
                    'app.user_auth_identities',
                    'DELETE'
                ),
                has_table_privilege(
                    'bff_control_writer',
                    'app.user_auth_identities',
                    'UPDATE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.user_auth_identities',
                    'status',
                    'UPDATE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.user_auth_identities',
                    'subject',
                    'UPDATE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.user_auth_identities',
                    'user_id',
                    'UPDATE'
                ),
                has_table_privilege(
                    'bff_runtime_writer',
                    'app.user_auth_identities',
                    'SELECT'
                ),
                has_table_privilege(
                    'bff_worker_writer',
                    'app.user_auth_identities',
                    'SELECT'
                ),
                has_table_privilege(
                    'bff_worker_writer',
                    'app.user_auth_identities',
                    'INSERT'
                ),
                has_table_privilege(
                    'bff_worker_writer',
                    'app.user_auth_identities',
                    'UPDATE'
                ),
                has_table_privilege(
                    'bff_retention',
                    'app.user_auth_identities',
                    'SELECT'
                )
            """
        ).fetchone()

    assert row == (
        True,
        True,
        False,
        False,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    )


def test_control_can_disable_auth_identity(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    _seed_identity(postgres_test_db)

    with postgres_test_db.role_connection("control") as connection:
        connection.execute(
            """
            UPDATE app.user_auth_identities
            SET
                status = 'DISABLED',
                updated_at = now(),
                disabled_at = now()
            WHERE id = %s
            """,
            (IDENTITY_ID,),
        )

        row = connection.execute(
            """
            SELECT status, disabled_at IS NOT NULL
            FROM app.user_auth_identities
            WHERE id = %s
            """,
            (IDENTITY_ID,),
        ).fetchone()

    assert row == ("DISABLED", True)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("user_id", "00000000-0000-7000-8000-000000000299"),
        ("issuer", "https://other-issuer.example"),
        ("subject", "other-subject"),
    ],
)
def test_control_cannot_reassign_auth_identity(
    postgres_test_db: DatabaseTestEnvironment,
    column: str,
    value: str,
) -> None:
    _seed_identity(postgres_test_db)

    with (
        postgres_test_db.role_connection("control") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            f"UPDATE app.user_auth_identities SET {column} = %s WHERE id = %s",
            (value, IDENTITY_ID),
        )


def test_control_cannot_delete_auth_identity(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    _seed_identity(postgres_test_db)

    with (
        postgres_test_db.role_connection("control") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            "DELETE FROM app.user_auth_identities WHERE id = %s",
            (IDENTITY_ID,),
        )


@pytest.mark.parametrize("role", ["runtime", "worker", "retention"])
def test_non_control_roles_cannot_read_auth_identities(
    postgres_test_db: DatabaseTestEnvironment,
    role: str,
) -> None:
    _seed_identity(postgres_test_db)

    with (
        postgres_test_db.role_connection(role) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("SELECT id FROM app.user_auth_identities LIMIT 1")
