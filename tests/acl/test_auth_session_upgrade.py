from __future__ import annotations

import os
import secrets

import psycopg
from alembic import command
from alembic.config import Config
from bff_control.core.settings import get_database_settings
from sqlalchemy import URL

import tests.support.database as database_support

PREVIOUS_REVISION = "0002_user_auth_identities"


def _upgrade(database_url: URL, revision: str) -> None:
    old_runtime = os.environ.get("BFF_DATABASE_URL")
    old_migration = os.environ.get("BFF_MIGRATION_DATABASE_URL")

    os.environ["BFF_DATABASE_URL"] = database_support._sqlalchemy_url(
        database_url,
        driver="postgresql+asyncpg",
    )
    os.environ["BFF_MIGRATION_DATABASE_URL"] = database_support._sqlalchemy_url(
        database_url,
        driver="postgresql+psycopg",
    )
    get_database_settings.cache_clear()

    try:
        config = Config(str(database_support.ROOT / "alembic.ini"))
        command.upgrade(config, revision)
    finally:
        if old_runtime is None:
            os.environ.pop("BFF_DATABASE_URL", None)
        else:
            os.environ["BFF_DATABASE_URL"] = old_runtime

        if old_migration is None:
            os.environ.pop("BFF_MIGRATION_DATABASE_URL", None)
        else:
            os.environ["BFF_MIGRATION_DATABASE_URL"] = old_migration

        get_database_settings.cache_clear()


def test_0003_revokes_inherited_worker_access_when_roles_already_exist() -> None:
    admin_url = database_support._required_admin_url()
    suffix = secrets.token_hex(6)
    database_name = f"bff_session_upgrade_{suffix}"
    database_url = database_support._create_database(admin_url, database_name)

    baseline_roles = (
        database_support.ROOT
        / "apps"
        / "control-api"
        / "migrations"
        / "sql"
        / "0001_database_roles_v2_1.sql"
    ).read_text(encoding="utf-8")

    try:
        _upgrade(database_url, PREVIOUS_REVISION)

        with psycopg.connect(
            database_support._postgres_dsn(database_url),
            autocommit=True,
        ) as connection:
            connection.execute(baseline_roles)

        _upgrade(database_url, "head")

        with psycopg.connect(
            database_support._postgres_dsn(database_url),
            autocommit=True,
        ) as connection:
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
                    has_column_privilege(
                        'bff_control_writer',
                        'app.auth_sessions',
                        'revoked_at',
                        'UPDATE'
                    ),
                    has_column_privilege(
                        'bff_control_writer',
                        'app.auth_sessions',
                        'expires_at',
                        'UPDATE'
                    ),
                    has_table_privilege(
                        'bff_worker_writer',
                        'app.auth_sessions',
                        'SELECT'
                    )
                """
            ).fetchone()

        assert row == (True, True, False, True, False, False)
    finally:
        database_support._drop_database_and_logins(
            admin_url,
            database_name,
            [],
        )
