from __future__ import annotations

from bff_control.infrastructure.db.database import Database
from bff_control.core.settings import DatabaseSettings


def test_database_engine_uses_asyncpg_driver() -> None:
    settings = DatabaseSettings(
        database_url="postgresql+asyncpg://user:secret@localhost:5432/bff",
        migration_database_url="postgresql+psycopg://user:secret@localhost:5432/bff",
    )

    database = Database(settings)

    try:
        assert database.engine.url.drivername == "postgresql+asyncpg"
    finally:
        # No connection is opened by engine construction, so sync test cleanup can
        # dispose the pool through the underlying engine without network I/O.
        database.engine.sync_engine.dispose(close=False)
