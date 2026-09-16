from __future__ import annotations

import psycopg
import pytest

from tests.support.database import DatabaseTestEnvironment


def _uuid(number: int) -> str:
    return f"00000000-0000-7000-8000-{number:012d}"


def _seed_user(
    postgres_test_db: DatabaseTestEnvironment,
    *,
    number: int,
) -> str:
    user_id = _uuid(number)
    email = f"identity-{number}@example.test"

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

    return user_id


def test_oidc_issuer_subject_pair_is_globally_unique(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_1 = _seed_user(postgres_test_db, number=201)
    user_2 = _seed_user(postgres_test_db, number=202)

    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (
                id,
                user_id,
                issuer,
                subject
            ) VALUES (%s, %s, %s, %s)
            """,
            (_uuid(211), user_1, "https://issuer.example", "subject-1"),
        )

        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO app.user_auth_identities (
                    id,
                    user_id,
                    issuer,
                    subject
                ) VALUES (%s, %s, %s, %s)
                """,
                (_uuid(212), user_2, "https://issuer.example", "subject-1"),
            )


def test_same_subject_from_different_issuers_is_allowed(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_1 = _seed_user(postgres_test_db, number=203)
    user_2 = _seed_user(postgres_test_db, number=204)

    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (id, user_id, issuer, subject)
            VALUES
                (%s, %s, 'https://issuer-a.example', 'same-subject'),
                (%s, %s, 'https://issuer-b.example', 'same-subject')
            """,
            (_uuid(213), user_1, _uuid(214), user_2),
        )


def test_identity_key_remains_case_sensitive(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_1 = _seed_user(postgres_test_db, number=205)
    user_2 = _seed_user(postgres_test_db, number=206)

    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (id, user_id, issuer, subject)
            VALUES
                (%s, %s, 'https://issuer.example', 'Subject'),
                (%s, %s, 'https://issuer.example', 'subject')
            """,
            (_uuid(215), user_1, _uuid(216), user_2),
        )


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        ("", "subject"),
        ("https://issuer.example", ""),
    ],
)
def test_identity_key_components_cannot_be_empty(
    postgres_test_db: DatabaseTestEnvironment,
    issuer: str,
    subject: str,
) -> None:
    user_id = _seed_user(postgres_test_db, number=207)

    with (
        postgres_test_db.owner_connection() as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (
                id,
                user_id,
                issuer,
                subject
            ) VALUES (%s, %s, %s, %s)
            """,
            (_uuid(217), user_id, issuer, subject),
        )


def test_disabled_identity_requires_disabled_at(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id = _seed_user(postgres_test_db, number=208)

    with (
        postgres_test_db.owner_connection() as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (
                id,
                user_id,
                issuer,
                subject,
                status
            ) VALUES (%s, %s, %s, %s, 'DISABLED')
            """,
            (_uuid(218), user_id, "https://issuer.example", "disabled-subject"),
        )


def test_active_identity_cannot_have_disabled_at(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id = _seed_user(postgres_test_db, number=209)

    with (
        postgres_test_db.owner_connection() as connection,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (
                id,
                user_id,
                issuer,
                subject,
                disabled_at
            ) VALUES (%s, %s, %s, %s, now())
            """,
            (_uuid(219), user_id, "https://issuer.example", "active-subject"),
        )


def test_identity_must_reference_existing_user(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with (
        postgres_test_db.owner_connection() as connection,
        pytest.raises(psycopg.errors.ForeignKeyViolation),
    ):
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (
                id,
                user_id,
                issuer,
                subject
            ) VALUES (%s, %s, %s, %s)
            """,
            (
                _uuid(220),
                _uuid(299),
                "https://issuer.example",
                "missing-user-subject",
            ),
        )
