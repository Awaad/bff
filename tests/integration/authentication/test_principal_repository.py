from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from bff_control.core.settings import DatabaseSettings
from bff_control.domains.authentication.models import VerifiedAccessToken
from bff_control.infrastructure.db.database import Database
from bff_control.infrastructure.db.principal_repository import (
    SqlAlchemyPrincipalRepository,
)

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


def _verified_token(
    *,
    subject: str,
    provider_session_id: str,
    issuer: str = "https://issuer.example",
) -> VerifiedAccessToken:
    now = datetime.now(tz=UTC)
    return VerifiedAccessToken(
        issuer=issuer,
        subject=subject,
        provider_session_id=provider_session_id,
        token_id=f"token-{subject}",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _seed(
    postgres_test_db: DatabaseTestEnvironment,
    *,
    base: int,
    user_status: str = "ACTIVE",
    identity_status: str = "ACTIVE",
    session_state: str = "ACTIVE",
) -> tuple[UUID, UUID, str, str]:
    now = datetime.now(tz=UTC)
    user_id = _uuid(base)
    identity_id = _uuid(base + 1)
    session_id = _uuid(base + 2)
    subject = f"subject-{base}"
    provider_session_id = f"provider-session-{base}"
    email = f"user-{base}@example.test"
    identity_disabled_at = now if identity_status == "DISABLED" else None
    revoked_at = now if session_state == "REVOKED" else None
    revocation_reason = "SECURITY_REVOKE" if revoked_at is not None else None
    created_at = now
    expires_at = now + timedelta(hours=1)

    if session_state == "EXPIRED":
        created_at = now - timedelta(hours=2)
        expires_at = now - timedelta(hours=1)

    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.users (
                id,
                email,
                email_normalized,
                display_name,
                status
            ) VALUES (%s, %s, %s, 'Current User', %s)
            """,
            (user_id, email, email, user_status),
        )
        connection.execute(
            """
            INSERT INTO app.user_auth_identities (
                id,
                user_id,
                issuer,
                subject,
                status,
                disabled_at
            ) VALUES (%s, %s, 'https://issuer.example', %s, %s, %s)
            """,
            (
                identity_id,
                user_id,
                subject,
                identity_status,
                identity_disabled_at,
            ),
        )
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
                session_id,
                identity_id,
                provider_session_id,
                expires_at,
                revoked_at,
                revocation_reason,
                created_at,
            ),
        )

    return UUID(user_id), UUID(session_id), subject, provider_session_id


@pytest.mark.parametrize(
    ("base", "user_status", "identity_status", "session_state"),
    [
        (520, "DISABLED", "ACTIVE", "ACTIVE"),
        (530, "ACTIVE", "DISABLED", "ACTIVE"),
        (540, "ACTIVE", "ACTIVE", "REVOKED"),
        (550, "ACTIVE", "ACTIVE", "EXPIRED"),
    ],
)
async def test_repository_rejects_inactive_admission_state(
    postgres_test_db: DatabaseTestEnvironment,
    base: int,
    user_status: str,
    identity_status: str,
    session_state: str,
) -> None:
    _, _, subject, provider_session_id = _seed(
        postgres_test_db,
        base=base,
        user_status=user_status,
        identity_status=identity_status,
        session_state=session_state,
    )
    database = _database(postgres_test_db)
    repository = SqlAlchemyPrincipalRepository(database)

    try:
        result = await repository.resolve_active_principal(
            _verified_token(
                subject=subject,
                provider_session_id=provider_session_id,
            )
        )
    finally:
        await database.dispose()

    assert result is None


async def test_repository_resolves_active_identity_user_and_session(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    user_id, session_id, subject, provider_session_id = _seed(
        postgres_test_db,
        base=510,
    )
    database = _database(postgres_test_db)
    repository = SqlAlchemyPrincipalRepository(database)

    try:
        result = await repository.resolve_active_principal(
            _verified_token(
                subject=subject,
                provider_session_id=provider_session_id,
            )
        )
    finally:
        await database.dispose()

    assert result is not None
    assert result.user_id == user_id
    assert result.auth_session_id == session_id
    assert result.email == "user-510@example.test"
    assert result.display_name == "Current User"


async def test_repository_requires_exact_provider_session_id(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    _, _, subject, _ = _seed(postgres_test_db, base=560)
    database = _database(postgres_test_db)
    repository = SqlAlchemyPrincipalRepository(database)

    try:
        result = await repository.resolve_active_principal(
            _verified_token(
                subject=subject,
                provider_session_id="different-session",
            )
        )
    finally:
        await database.dispose()

    assert result is None


async def test_repository_requires_exact_issuer(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    _, _, subject, provider_session_id = _seed(postgres_test_db, base=570)
    database = _database(postgres_test_db)
    repository = SqlAlchemyPrincipalRepository(database)

    try:
        result = await repository.resolve_active_principal(
            _verified_token(
                subject=subject,
                provider_session_id=provider_session_id,
                issuer="https://different-issuer.example",
            )
        )
    finally:
        await database.dispose()

    assert result is None
