from __future__ import annotations

import psycopg
import pytest

from tests.support.database import DatabaseTestEnvironment


def _uuid(number: int) -> str:
    return f"00000000-0000-7000-8000-{number:012d}"


def _seed_session(
    postgres_test_db: DatabaseTestEnvironment,
    *,
    user_number: int,
    identity_number: int,
    session_number: int,
) -> str:
    user_id = _uuid(user_number)
    identity_id = _uuid(identity_number)
    session_id = _uuid(session_number)
    email = f"session-acl-{user_number}@example.test"

    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.users (
                id,
                email,
                email_normalized
            ) VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (user_id, email, email),
        )
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (
                id,
                user_id,
                issuer,
                subject
            ) VALUES (%s, %s, 'https://issuer.example', %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (identity_id, user_id, f"session-acl-subject-{identity_number}"),
        )
        connection.execute(
            """
            INSERT INTO app.auth_sessions (
                id,
                user_auth_identity_id,
                provider_session_id,
                expires_at
            ) VALUES (%s, %s, %s, now() + interval '1 day')
            ON CONFLICT (id) DO NOTHING
            """,
            (
                session_id,
                identity_id,
                f"session-acl-provider-{session_number}",
            ),
        )

    return session_id


def test_auth_session_role_surface_is_least_privilege(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.owner_connection() as connection:
        row = connection.execute(
            """
            SELECT
                has_table_privilege(
                    'bff_control_writer',
                    'app.auth_sessions',
                    'SELECT'
                ),
                has_table_privilege(
                    'bff_control_writer',
                    'app.auth_sessions',
                    'INSERT'
                ),
                has_table_privilege(
                    'bff_control_writer',
                    'app.auth_sessions',
                    'UPDATE'
                ),
                has_table_privilege(
                    'bff_control_writer',
                    'app.auth_sessions',
                    'DELETE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.auth_sessions',
                    'revoked_at',
                    'UPDATE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.auth_sessions',
                    'provider_revoked_at',
                    'UPDATE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.auth_sessions',
                    'expires_at',
                    'UPDATE'
                ),
                has_column_privilege(
                    'bff_control_writer',
                    'app.auth_sessions',
                    'provider_session_id',
                    'UPDATE'
                ),
                has_table_privilege(
                    'bff_runtime_writer',
                    'app.auth_sessions',
                    'SELECT'
                ),
                has_table_privilege(
                    'bff_worker_writer',
                    'app.auth_sessions',
                    'SELECT'
                ),
                has_table_privilege(
                    'bff_retention',
                    'app.auth_sessions',
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
        True,
        False,
        False,
        False,
        False,
        False,
    )


def test_control_can_revoke_auth_session(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    session_id = _seed_session(
        postgres_test_db,
        user_number=401,
        identity_number=411,
        session_number=421,
    )

    with postgres_test_db.role_connection("control") as connection:
        connection.execute(
            """
            UPDATE app.auth_sessions
            SET
                revoked_at = now(),
                revocation_reason = 'LOCAL_LOGOUT',
                updated_at = now()
            WHERE id = %s
            """,
            (session_id,),
        )
        row = connection.execute(
            """
            SELECT revoked_at IS NOT NULL, revocation_reason
            FROM app.auth_sessions
            WHERE id = %s
            """,
            (session_id,),
        ).fetchone()

    assert row == (True, "LOCAL_LOGOUT")


@pytest.mark.parametrize(
    ("column", "value_sql", "user_number", "identity_number", "session_number"),
    [
        (
            "user_auth_identity_id",
            "'00000000-0000-7000-8000-000000000499'::uuid",
            402,
            412,
            422,
        ),
        (
            "provider_session_id",
            "'changed-provider-session'",
            403,
            413,
            423,
        ),
        (
            "expires_at",
            "now() + interval '2 days'",
            404,
            414,
            424,
        ),
        (
            "created_at",
            "now() - interval '1 day'",
            405,
            415,
            425,
        ),
    ],
)
def test_control_cannot_mutate_auth_session_identity_or_absolute_ttl(
    postgres_test_db: DatabaseTestEnvironment,
    column: str,
    value_sql: str,
    user_number: int,
    identity_number: int,
    session_number: int,
) -> None:
    session_id = _seed_session(
        postgres_test_db,
        user_number=user_number,
        identity_number=identity_number,
        session_number=session_number,
    )

    with (
        postgres_test_db.role_connection("control") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            f"UPDATE app.auth_sessions SET {column} = {value_sql} WHERE id = %s",
            (session_id,),
        )


@pytest.mark.parametrize(
    ("role", "user_number", "identity_number", "session_number"),
    [
        ("runtime", 406, 416, 426),
        ("worker", 407, 417, 427),
        ("retention", 408, 418, 428),
    ],
)
def test_non_control_roles_cannot_read_auth_sessions(
    postgres_test_db: DatabaseTestEnvironment,
    role: str,
    user_number: int,
    identity_number: int,
    session_number: int,
) -> None:
    _seed_session(
        postgres_test_db,
        user_number=user_number,
        identity_number=identity_number,
        session_number=session_number,
    )

    with (
        postgres_test_db.role_connection(role) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("SELECT id FROM app.auth_sessions LIMIT 1")
