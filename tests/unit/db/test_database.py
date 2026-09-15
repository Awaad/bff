from __future__ import annotations

from pydantic import SecretStr

from bff_control.core.settings import DatabaseSettings
from bff_control.infrastructure.db.database import Database


def test_database_engine_uses_asyncpg_driver() -> None:
    settings = DatabaseSettings(
        database_url=SecretStr(
            "postgresql+asyncpg://user:secret@localhost:5432/bff",
        ),
        migration_database_url=SecretStr(
            "postgresql+psycopg://user:secret@localhost:5432/bff",
        ),
    )

    database = Database(settings)

    try:
        assert database.engine.url.drivername == "postgresql+asyncpg"
    finally:
        database.engine.sync_engine.dispose(close=False)