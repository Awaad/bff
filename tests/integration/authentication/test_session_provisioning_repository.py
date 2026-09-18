from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from bff_control.core.settings import DatabaseSettings
from bff_control.domains.authentication.models import VerifiedAccessToken
from bff_control.domains.authentication.provisioning_contracts import (
    AccountLinkRequiredError,
    SessionProvisioningAuthenticationError,
)
from bff_control.domains.authentication.provisioning_models import ExternalUserProfile
from bff_control.infrastructure.db.database import Database
from bff_control.infrastructure.db.session_provisioning_repository import (
    SqlAlchemySessionProvisioningRepository,
)

from tests.support.database import DatabaseTestEnvironment

pytestmark = [pytest.mark.postgres, pytest.mark.asyncio]


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


def _token(base: int, *, sid: str | None = None) -> VerifiedAccessToken:
    now = datetime.now(tz=UTC)
    return VerifiedAccessToken(
        issuer="https://issuer.example",
        subject=f"subject-{base}",
        provider_session_id=sid or f"session-{base}",
        token_id=f"token-{base}",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _profile(base: int, *, email: str | None = None) -> ExternalUserProfile:
    return ExternalUserProfile(
        subject=f"subject-{base}",
        email=email or f"User-{base}@Example.Test",
        email_verified=True,
        display_name=f"User {base}",
    )


async def test_first_provision_creates_user_identity_session_and_audit(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    database = _database(postgres_test_db)
    repository = SqlAlchemySessionProvisioningRepository(database)
    token = _token(801)

    try:
        result = await repository.provision_new_identity(
            token,
            _profile(801),
            ttl_seconds=604_800,
        )
    finally:
        await database.dispose()

    assert result.created is True
    assert result.principal.email == "User-801@Example.Test"

    with postgres_test_db.owner_connection() as connection:
        user_row = connection.execute(
            """
            SELECT email, email_normalized
            FROM app.users
            WHERE id = %s
            """,
            (result.principal.user_id,),
        ).fetchone()
        audit_count = connection.execute(
            """
            SELECT count(*)
            FROM app.audit_events
            WHERE resource_type = 'AUTH_SESSION'
              AND resource_id = %s
              AND action = 'AUTH_SESSION_CREATED'
            """,
            (result.principal.auth_session_id,),
        ).fetchone()

    assert user_row == ("User-801@Example.Test", "user-801@example.test")
    assert audit_count == (1,)


async def test_repeated_same_sid_is_idempotent_without_ttl_or_audit_extension(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    database = _database(postgres_test_db)
    repository = SqlAlchemySessionProvisioningRepository(database)
    token = _token(802)

    try:
        first = await repository.provision_new_identity(
            token,
            _profile(802),
            ttl_seconds=604_800,
        )
        identity = await repository.find_identity(token)
        assert identity is not None
        second = await repository.admit_existing_identity(
            token,
            identity,
            ttl_seconds=604_800,
        )
    finally:
        await database.dispose()

    assert first.created is True
    assert second.created is False
    assert second.principal.auth_session_id == first.principal.auth_session_id
    assert second.expires_at == first.expires_at

    with postgres_test_db.owner_connection() as connection:
        audit_count = connection.execute(
            """
            SELECT count(*)
            FROM app.audit_events
            WHERE resource_type = 'AUTH_SESSION'
              AND resource_id = %s
              AND action = 'AUTH_SESSION_CREATED'
            """,
            (first.principal.auth_session_id,),
        ).fetchone()

    assert audit_count == (1,)


async def test_email_collision_requires_explicit_account_link(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.owner_connection() as connection:
        connection.execute(
            """
            INSERT INTO app.users (id, email, email_normalized)
            VALUES (
                '00000000-0000-7000-8000-000000000803',
                'existing@example.test',
                'existing@example.test'
            )
            """
        )

    database = _database(postgres_test_db)
    repository = SqlAlchemySessionProvisioningRepository(database)

    try:
        with pytest.raises(AccountLinkRequiredError):
            await repository.provision_new_identity(
                _token(803),
                _profile(803, email=" Existing@Example.Test "),
                ttl_seconds=604_800,
            )
    finally:
        await database.dispose()


@pytest.mark.parametrize(
    ("base", "state"),
    [
        (804, "REVOKED"),
        (806, "EXPIRED"),
    ],
)
async def test_revoked_or_expired_same_sid_is_not_resurrected(
    postgres_test_db: DatabaseTestEnvironment,
    base: int,
    state: str,
) -> None:
    database = _database(postgres_test_db)
    repository = SqlAlchemySessionProvisioningRepository(database)
    token = _token(base)

    try:
        first = await repository.provision_new_identity(
            token,
            _profile(base),
            ttl_seconds=604_800,
        )
        identity = await repository.find_identity(token)
        assert identity is not None

        with postgres_test_db.owner_connection() as connection:
            if state == "REVOKED":
                connection.execute(
                    """
                    UPDATE app.auth_sessions
                    SET revoked_at = now(), revocation_reason = 'SECURITY_REVOKE'
                    WHERE id = %s
                    """,
                    (first.principal.auth_session_id,),
                )
            else:
                connection.execute(
                    """
                    UPDATE app.auth_sessions
                    SET
                        created_at = now() - interval '2 hours',
                        expires_at = now() - interval '1 hour'
                    WHERE id = %s
                    """,
                    (first.principal.auth_session_id,),
                )

        with pytest.raises(SessionProvisioningAuthenticationError):
            await repository.admit_existing_identity(
                token,
                identity,
                ttl_seconds=604_800,
            )
    finally:
        await database.dispose()


async def test_concurrent_first_provision_converges_to_one_identity_and_session(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    database = _database(postgres_test_db)
    repository = SqlAlchemySessionProvisioningRepository(database)
    token = _token(805)
    profile = _profile(805)

    try:
        first, second = await asyncio.gather(
            repository.provision_new_identity(
                token,
                profile,
                ttl_seconds=604_800,
            ),
            repository.provision_new_identity(
                token,
                profile,
                ttl_seconds=604_800,
            ),
        )
    finally:
        await database.dispose()

    assert first.principal.user_id == second.principal.user_id
    assert first.principal.auth_session_id == second.principal.auth_session_id
    assert sorted([first.created, second.created]) == [False, True]
