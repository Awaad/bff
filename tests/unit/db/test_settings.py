from __future__ import annotations

import pytest
from pydantic import ValidationError

from bff_control.core.settings import DatabaseSettings


def test_database_urls_require_explicit_runtime_and_migration_drivers() -> None:
    settings = DatabaseSettings(
        database_url="postgresql+asyncpg://user:secret@localhost:5432/bff",
        migration_database_url="postgresql+psycopg://user:secret@localhost:5432/bff",
    )

    assert settings.database_url.get_secret_value().startswith("postgresql+asyncpg://")
    assert settings.migration_database_url.get_secret_value().startswith(
        "postgresql+psycopg://",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "postgresql+psycopg://user:secret@localhost/bff"),
        ("migration_database_url", "postgresql+asyncpg://user:secret@localhost/bff"),
    ],
)
def test_database_urls_reject_wrong_driver(field: str, value: str) -> None:
    values = {
        "database_url": "postgresql+asyncpg://user:secret@localhost/bff",
        "migration_database_url": "postgresql+psycopg://user:secret@localhost/bff",
    }
    values[field] = value

    with pytest.raises(ValidationError):
        DatabaseSettings(**values)


def test_database_settings_repr_redacts_passwords() -> None:
    settings = DatabaseSettings(
        database_url="postgresql+asyncpg://user:super-secret@localhost/bff",
        migration_database_url="postgresql+psycopg://user:other-secret@localhost/bff",
    )

    representation = repr(settings)

    assert "super-secret" not in representation
    assert "other-secret" not in representation
