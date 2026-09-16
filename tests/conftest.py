from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from psycopg import Connection

from tests.support.database import DatabaseTestEnvironment, provision_database

ROOT = Path(__file__).resolve().parents[1]
APPLICATION_ROLES_SQL = (
    ROOT / "apps" / "control-api" / "migrations" / "sql" / "application_roles.sql"
)
POSTGRES_TEST_ROOTS = (
    ROOT / "tests" / "schema",
    ROOT / "tests" / "acl",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Classify database-dependent tests by directory."""

    for item in items:
        if any(item.path.is_relative_to(root) for root in POSTGRES_TEST_ROOTS):
            item.add_marker(pytest.mark.postgres)


def _apply_current_application_roles(
    environment: DatabaseTestEnvironment,
) -> None:
    role_sql = APPLICATION_ROLES_SQL.read_text(encoding="utf-8")
    with environment.owner_connection() as connection:
        connection.execute(role_sql)


@pytest.fixture(scope="session")
def postgres_test_db() -> Iterator[DatabaseTestEnvironment]:
    with provision_database() as environment:
        _apply_current_application_roles(environment)
        yield environment


@pytest.fixture
def owner_db(
    postgres_test_db: DatabaseTestEnvironment,
) -> Iterator[Connection[tuple[object, ...]]]:
    with postgres_test_db.owner_connection() as connection:
        yield connection
