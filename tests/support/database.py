"""Disposable PostgreSQL environment for schema and ACL regression tests."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import Connection, sql
from sqlalchemy import URL, make_url

from bff_control.core.settings import get_database_settings

ROOT = Path(__file__).resolve().parents[2]
ROLES_SQL = (
    ROOT
    / "apps"
    / "control-api"
    / "migrations"
    / "sql"
    / "0001_database_roles_v2_1.sql"
)

GROUP_ROLES = {
    "control": "bff_control_writer",
    "runtime": "bff_runtime_writer",
    "worker": "bff_worker_writer",
    "retention": "bff_retention",
}


def _postgres_dsn(url: URL) -> str:
    driver = url.drivername
    if driver not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError(
            "BFF_TEST_ADMIN_URL must use postgresql or postgresql+psycopg",
        )

    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _sqlalchemy_url(url: URL, *, driver: str) -> str:
    return url.set(drivername=driver).render_as_string(hide_password=False)


@dataclass(frozen=True)
class DatabaseTestEnvironment:
    """Connection information for one disposable migrated database."""

    database_name: str
    owner_url: URL
    login_urls: dict[str, URL]

    @contextmanager
    def owner_connection(self) -> Iterator[Connection[tuple[object, ...]]]:
        with psycopg.connect(
            _postgres_dsn(self.owner_url),
            autocommit=True,
        ) as connection:
            yield connection

    @contextmanager
    def role_connection(
        self,
        role: str,
    ) -> Iterator[Connection[tuple[object, ...]]]:
        try:
            role_url = self.login_urls[role]
        except KeyError as error:
            raise KeyError(f"unknown database test role: {role}") from error

        with psycopg.connect(
            _postgres_dsn(role_url),
            autocommit=True,
        ) as connection:
            yield connection


def _required_admin_url() -> URL:
    raw = os.environ.get("BFF_TEST_ADMIN_URL")
    if raw is None or not raw.strip():
        raise RuntimeError(
            "BFF_TEST_ADMIN_URL is required for PostgreSQL schema/ACL tests; "
            "point it at a disposable-capable PostgreSQL admin database",
        )

    return make_url(raw)


def _create_database(admin_url: URL, database_name: str) -> URL:
    with psycopg.connect(_postgres_dsn(admin_url), autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)),
        )

    return admin_url.set(database=database_name)


def _run_migrations(database_url: URL) -> None:
    old_runtime = os.environ.get("BFF_DATABASE_URL")
    old_migration = os.environ.get("BFF_MIGRATION_DATABASE_URL")

    os.environ["BFF_DATABASE_URL"] = _sqlalchemy_url(
        database_url,
        driver="postgresql+asyncpg",
    )
    os.environ["BFF_MIGRATION_DATABASE_URL"] = _sqlalchemy_url(
        database_url,
        driver="postgresql+psycopg",
    )
    get_database_settings.cache_clear()

    try:
        alembic_config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(alembic_config, "head")
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


def _apply_application_roles(database_url: URL) -> None:
    role_sql = ROLES_SQL.read_text(encoding="utf-8")

    with psycopg.connect(_postgres_dsn(database_url), autocommit=True) as connection:
        connection.execute(role_sql)


def _create_login_principals(
    admin_url: URL,
    database_url: URL,
    suffix: str,
) -> tuple[dict[str, URL], list[str]]:
    login_urls: dict[str, URL] = {}
    role_names: list[str] = []

    with psycopg.connect(_postgres_dsn(admin_url), autocommit=True) as connection:
        for logical_name, group_role in GROUP_ROLES.items():
            login_role = f"bff_test_{logical_name}_{suffix}"
            password = secrets.token_urlsafe(24)

            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN INHERIT PASSWORD %s").format(
                    sql.Identifier(login_role),
                ),
                (password,),
            )
            connection.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(group_role),
                    sql.Identifier(login_role),
                ),
            )

            login_urls[logical_name] = database_url.set(
                username=login_role,
                password=password,
            )
            role_names.append(login_role)

    return login_urls, role_names


def _drop_database_and_logins(
    admin_url: URL,
    database_name: str,
    login_roles: list[str],
) -> None:
    with psycopg.connect(_postgres_dsn(admin_url), autocommit=True) as connection:
        connection.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s
              AND pid <> pg_backend_pid()
            """,
            (database_name,),
        )
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(
                sql.Identifier(database_name),
            ),
        )

        for role_name in login_roles:
            connection.execute(
                sql.SQL("DROP ROLE IF EXISTS {}").format(
                    sql.Identifier(role_name),
                ),
            )


@contextmanager
def provision_database() -> Iterator[DatabaseTestEnvironment]:
    """Create, migrate and later destroy an isolated PostgreSQL test database."""

    admin_url = _required_admin_url()
    suffix = secrets.token_hex(6)
    database_name = f"bff_test_{suffix}"
    database_url: URL | None = None
    login_roles: list[str] = []

    try:
        database_url = _create_database(admin_url, database_name)
        _run_migrations(database_url)
        _apply_application_roles(database_url)
        login_urls, login_roles = _create_login_principals(
            admin_url,
            database_url,
            suffix,
        )

        environment = DatabaseTestEnvironment(
            database_name=database_name,
            owner_url=database_url,
            login_urls=login_urls,
        )

        with environment.owner_connection() as connection:
            seed_valid_graph(connection)

        yield environment
    finally:
        _drop_database_and_logins(
            admin_url,
            database_name,
            login_roles,
        )


IDS = {
    "workspace_1": "00000000-0000-7000-8000-000000000001",
    "workspace_2": "00000000-0000-7000-8000-000000000002",
    "project_1": "00000000-0000-7000-8000-000000000011",
    "project_2": "00000000-0000-7000-8000-000000000012",
    "project_3": "00000000-0000-7000-8000-000000000013",
    "framer_auth_1": "00000000-0000-7000-8000-000000000021",
    "framer_auth_2": "00000000-0000-7000-8000-000000000022",
    "connection_1": "00000000-0000-7000-8000-000000000031",
    "connection_2": "00000000-0000-7000-8000-000000000032",
    "connection_revision_1": "00000000-0000-7000-8000-000000000041",
    "connection_revision_2": "00000000-0000-7000-8000-000000000042",
    "credential_1": "00000000-0000-7000-8000-000000000051",
    "credential_2": "00000000-0000-7000-8000-000000000052",
    "credential_revision_1": "00000000-0000-7000-8000-000000000061",
    "credential_revision_2": "00000000-0000-7000-8000-000000000062",
    "operation_1": "00000000-0000-7000-8000-000000000071",
    "operation_version_1": "00000000-0000-7000-8000-000000000081",
    "operation_version_2": "00000000-0000-7000-8000-000000000082",
    "binding_public": "00000000-0000-7000-8000-000000000091",
    "binding_internal": "00000000-0000-7000-8000-000000000092",
    "binding_acl": "00000000-0000-7000-8000-000000000093",
    "binding_revision_public": "00000000-0000-7000-8000-000000000101",
    "binding_revision_internal": "00000000-0000-7000-8000-000000000102",
    "binding_revision_acl": "00000000-0000-7000-8000-000000000103",
    "sync_definition": "00000000-0000-7000-8000-000000000111",
    "sync_revision": "00000000-0000-7000-8000-000000000112",
    "execution_acl": "00000000-0000-7000-8000-000000000121",
    "execution_attempt_acl": "00000000-0000-7000-8000-000000000122",
}


def seed_valid_graph(connection: Connection[tuple[object, ...]]) -> None:
    """Insert the smallest valid graph needed by schema and ACL probes."""

    statements: list[tuple[str, dict[str, str]]] = [
        (
            """
            INSERT INTO app.workspaces (id, name) VALUES
                (%(workspace_1)s, 'Workspace One'),
                (%(workspace_2)s, 'Workspace Two')
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.projects (id, workspace_id, name) VALUES
                (%(project_1)s, %(workspace_1)s, 'Project One'),
                (%(project_2)s, %(workspace_1)s, 'Project Two'),
                (%(project_3)s, %(workspace_2)s, 'Project Three')
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.framer_authorizations (id, workspace_id) VALUES
                (%(framer_auth_1)s, %(workspace_1)s),
                (%(framer_auth_2)s, %(workspace_2)s)
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.connections (
                id, workspace_id, name, provider_key, status
            ) VALUES
                (%(connection_1)s, %(workspace_1)s, 'Connection One', 'fixture', 'ACTIVE'),
                (%(connection_2)s, %(workspace_1)s, 'Connection Two', 'fixture', 'ACTIVE')
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.connection_revisions (
                id,
                workspace_id,
                connection_id,
                revision_number,
                definition_schema_version,
                config_json,
                config_hash
            ) VALUES
                (
                    %(connection_revision_1)s,
                    %(workspace_1)s,
                    %(connection_1)s,
                    1,
                    1,
                    '{}'::jsonb,
                    decode('01', 'hex')
                ),
                (
                    %(connection_revision_2)s,
                    %(workspace_1)s,
                    %(connection_2)s,
                    1,
                    1,
                    '{}'::jsonb,
                    decode('02', 'hex')
                )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.credentials (
                id,
                workspace_id,
                connection_id,
                name,
                auth_scheme
            ) VALUES
                (
                    %(credential_1)s,
                    %(workspace_1)s,
                    %(connection_1)s,
                    'No auth one',
                    'NONE'
                ),
                (
                    %(credential_2)s,
                    %(workspace_1)s,
                    %(connection_2)s,
                    'No auth two',
                    'NONE'
                )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.credential_revisions (
                id,
                workspace_id,
                connection_id,
                credential_id,
                revision_number,
                auth_scheme,
                config_json,
                config_hash
            ) VALUES
                (
                    %(credential_revision_1)s,
                    %(workspace_1)s,
                    %(connection_1)s,
                    %(credential_1)s,
                    1,
                    'NONE',
                    '{}'::jsonb,
                    decode('11', 'hex')
                ),
                (
                    %(credential_revision_2)s,
                    %(workspace_1)s,
                    %(connection_2)s,
                    %(credential_2)s,
                    1,
                    'NONE',
                    '{}'::jsonb,
                    decode('12', 'hex')
                )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.operations (
                id,
                workspace_id,
                connection_id,
                name,
                status
            ) VALUES (
                %(operation_1)s,
                %(workspace_1)s,
                %(connection_1)s,
                'Read operation',
                'ACTIVE'
            )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.operation_versions (
                id,
                workspace_id,
                connection_id,
                operation_id,
                version_number,
                definition_schema_version,
                effect,
                request_body_mode,
                response_mode,
                definition_json,
                definition_hash
            ) VALUES
                (
                    %(operation_version_1)s,
                    %(workspace_1)s,
                    %(connection_1)s,
                    %(operation_1)s,
                    1,
                    1,
                    'READ',
                    'NONE',
                    'JSON',
                    '{}'::jsonb,
                    decode('21', 'hex')
                ),
                (
                    %(operation_version_2)s,
                    %(workspace_1)s,
                    %(connection_1)s,
                    %(operation_1)s,
                    2,
                    1,
                    'READ',
                    'NONE',
                    'JSON',
                    '{}'::jsonb,
                    decode('22', 'hex')
                )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.bindings (
                id,
                workspace_id,
                project_id,
                name,
                kind,
                exposure_mode,
                status
            ) VALUES
                (
                    %(binding_public)s,
                    %(workspace_1)s,
                    %(project_1)s,
                    'Public fixture',
                    'QUERY',
                    'PUBLIC',
                    'ACTIVE'
                ),
                (
                    %(binding_internal)s,
                    %(workspace_1)s,
                    %(project_1)s,
                    'Internal fixture',
                    'QUERY',
                    'INTERNAL',
                    'ACTIVE'
                ),
                (
                    %(binding_acl)s,
                    %(workspace_1)s,
                    %(project_1)s,
                    'ACL fixture',
                    'ACTION',
                    'INTERNAL',
                    'ACTIVE'
                )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.binding_revisions (
                id,
                workspace_id,
                project_id,
                binding_id,
                revision_number,
                connection_id,
                connection_revision_id,
                operation_id,
                operation_version_id,
                credential_id,
                credential_revision_id,
                compiled_config_json,
                config_hash
            ) VALUES
                (
                    %(binding_revision_public)s,
                    %(workspace_1)s,
                    %(project_1)s,
                    %(binding_public)s,
                    1,
                    %(connection_1)s,
                    %(connection_revision_1)s,
                    %(operation_1)s,
                    %(operation_version_1)s,
                    %(credential_1)s,
                    %(credential_revision_1)s,
                    '{}'::jsonb,
                    decode('31', 'hex')
                ),
                (
                    %(binding_revision_internal)s,
                    %(workspace_1)s,
                    %(project_1)s,
                    %(binding_internal)s,
                    1,
                    %(connection_1)s,
                    %(connection_revision_1)s,
                    %(operation_1)s,
                    %(operation_version_1)s,
                    %(credential_1)s,
                    %(credential_revision_1)s,
                    '{}'::jsonb,
                    decode('32', 'hex')
                ),
                (
                    %(binding_revision_acl)s,
                    %(workspace_1)s,
                    %(project_1)s,
                    %(binding_acl)s,
                    1,
                    %(connection_1)s,
                    %(connection_revision_1)s,
                    %(operation_1)s,
                    %(operation_version_1)s,
                    %(credential_1)s,
                    %(credential_revision_1)s,
                    '{}'::jsonb,
                    decode('33', 'hex')
                )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.sync_definitions (
                id,
                workspace_id,
                project_id,
                name,
                status
            ) VALUES (
                %(sync_definition)s,
                %(workspace_1)s,
                %(project_1)s,
                'Sync fixture',
                'ACTIVE'
            )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.sync_revisions (
                id,
                workspace_id,
                project_id,
                sync_definition_id,
                revision_number,
                source_adapter_key,
                source_config_json,
                target_adapter_key,
                target_config_json,
                source_binding_id,
                identity_strategy_json,
                mapping_json,
                config_hash
            ) VALUES (
                %(sync_revision)s,
                %(workspace_1)s,
                %(project_1)s,
                %(sync_definition)s,
                1,
                'binding',
                '{}'::jsonb,
                'fixture-target',
                '{}'::jsonb,
                %(binding_public)s,
                '{}'::jsonb,
                '{}'::jsonb,
                decode('41', 'hex')
            )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.executions (
                id,
                public_execution_ref,
                workspace_id,
                project_id,
                lineage_mode,
                binding_id,
                binding_revision_id,
                operation_id,
                operation_version_id,
                connection_id,
                connection_revision_id,
                credential_id,
                credential_revision_id,
                source,
                status
            ) VALUES (
                %(execution_acl)s,
                'exec_acl_fixture',
                %(workspace_1)s,
                %(project_1)s,
                'BINDING',
                %(binding_acl)s,
                %(binding_revision_acl)s,
                %(operation_1)s,
                %(operation_version_1)s,
                %(connection_1)s,
                %(connection_revision_1)s,
                %(credential_1)s,
                %(credential_revision_1)s,
                'ACTION',
                'RUNNING'
            )
            """,
            IDS,
        ),
        (
            """
            INSERT INTO app.execution_attempts (
                id,
                workspace_id,
                execution_id,
                attempt_number,
                status
            ) VALUES (
                %(execution_attempt_acl)s,
                %(workspace_1)s,
                %(execution_acl)s,
                1,
                'RUNNING'
            )
            """,
            IDS,
        ),
    ]

    for statement, parameters in statements:
        connection.execute(statement, parameters)
