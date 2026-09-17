from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from tests.support.database import DatabaseTestEnvironment


def _uuid(number: int) -> str:
    return f"00000000-0000-7000-8000-{number:012d}"


def _seed_identity(
    postgres_test_db: DatabaseTestEnvironment,
    *,
    user_number: int,
    identity_number: int,
    subject: str,
) -> str:
    user_id = _uuid(user_number)
    identity_id = _uuid(identity_number)
    email = f"session-{user_number}@example.test"

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
            (identity_id, user_id, subject),
        )

    return identity_id


def test_provider_session_id_is_unique_per_identity(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    identity_id = _seed_identity(
        postgres_test_db,
        user_number=301,
        identity_number=311,
        subject="subject-301",
    )

    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.auth_sessions (
                id,
                user_auth_identity_id,
                provider_session_id,
                expires_at
            ) VALUES (%s, %s, 'provider-session-301', now() + interval '1 hour')
            """,
            (_uuid(321), identity_id),
        )

        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO app.auth_sessions (
                    id,
                    user_auth_identity_id,
                    provider_session_id,
                    expires_at
                ) VALUES (%s, %s, 'provider-session-301', now() + interval '1 hour')
                """,
                (_uuid(322), identity_id),
            )


def test_same_provider_session_id_can_exist_for_different_identities(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    identity_1 = _seed_identity(
        postgres_test_db,
        user_number=302,
        identity_number=312,
        subject="subject-302",
    )
    identity_2 = _seed_identity(
        postgres_test_db,
        user_number=303,
        identity_number=313,
        subject="subject-303",
    )

    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.auth_sessions (
                id,
                user_auth_identity_id,
                provider_session_id,
                expires_at
            ) VALUES
                (%s, %s, 'shared-provider-session', now() + interval '1 hour'),
                (%s, %s, 'shared-provider-session', now() + interval '1 hour')
            """,
            (_uuid(323), identity_1, _uuid(324), identity_2),
        )


def test_session_expiry_must_be_after_creation(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    identity_id = _seed_identity(
        postgres_test_db,
        user_number=304,
        identity_number=314,
        subject="subject-304",
    )
    created_at = datetime(2026, 1, 1, tzinfo=UTC)

    with (
        postgres_test_db.owner_connection() as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            """
            INSERT INTO app.auth_sessions (
                id,
                user_auth_identity_id,
                provider_session_id,
                expires_at,
                created_at
            ) VALUES (%s, %s, 'expired-at-create', %s, %s)
            """,
            (_uuid(325), identity_id, created_at, created_at),
        )


@pytest.mark.parametrize(
    ("revoked_at", "reason", "user_number", "identity_number", "session_number"),
    [
        (
            datetime(2026, 1, 1, tzinfo=UTC),
            None,
            305,
            315,
            326,
        ),
        (
            None,
            "LOCAL_LOGOUT",
            306,
            316,
            327,
        ),
        (
            datetime(2026, 1, 1, tzinfo=UTC),
            "",
            307,
            317,
            328,
        ),
    ],
)
def test_revocation_timestamp_and_reason_are_pair_complete(
    postgres_test_db: DatabaseTestEnvironment,
    revoked_at: datetime | None,
    reason: str | None,
    user_number: int,
    identity_number: int,
    session_number: int,
) -> None:
    identity_id = _seed_identity(
        postgres_test_db,
        user_number=user_number,
        identity_number=identity_number,
        subject=f"subject-{user_number}",
    )
    expires_at = datetime(2026, 1, 2, tzinfo=UTC)
    created_at = datetime(2026, 1, 1, tzinfo=UTC) - timedelta(hours=1)

    with (
        postgres_test_db.owner_connection() as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            """
            INSERT INTO app.auth_sessions (
                id,
                user_auth_identity_id,
                provider_session_id,
                expires_at,
                revoked_at,
                revocation_reason,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                _uuid(session_number),
                identity_id,
                f"revocation-pair-{session_number}",
                expires_at,
                revoked_at,
                reason,
                created_at,
            ),
        )


def test_provider_revocation_requires_local_revocation_state(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    identity_id = _seed_identity(
        postgres_test_db,
        user_number=308,
        identity_number=318,
        subject="subject-308",
    )

    with (
        postgres_test_db.owner_connection() as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            """
            INSERT INTO app.auth_sessions (
                id,
                user_auth_identity_id,
                provider_session_id,
                expires_at,
                provider_revoked_at
            ) VALUES (
                %s,
                %s,
                'provider-revoked-only',
                now() + interval '1 hour',
                now()
            )
            """,
            (_uuid(329), identity_id),
        )


def test_session_must_reference_existing_identity(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with (
        postgres_test_db.owner_connection() as connection,
        pytest.raises(psycopg.errors.ForeignKeyViolation),
    ):
        connection.execute(
            """
            INSERT INTO app.auth_sessions (
                id,
                user_auth_identity_id,
                provider_session_id,
                expires_at
            ) VALUES (%s, %s, 'missing-identity', now() + interval '1 hour')
            """,
            (_uuid(330), _uuid(399)),
        )
