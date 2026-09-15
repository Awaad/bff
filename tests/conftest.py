from __future__ import annotations

from collections.abc import Iterator

import pytest
from psycopg import Connection

from tests.support.database import DatabaseTestEnvironment, provision_database


@pytest.fixture(scope="session")
def postgres_test_db() -> Iterator[DatabaseTestEnvironment]:
    with provision_database() as environment:
        yield environment


@pytest.fixture
def owner_db(
    postgres_test_db: DatabaseTestEnvironment,
) -> Iterator[Connection[tuple[object, ...]]]:
    with postgres_test_db.owner_connection() as connection:
        yield connection
