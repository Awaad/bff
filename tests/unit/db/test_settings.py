from __future__ import annotations

import pytest
from bff_control.core.settings import DatabaseSettings
from pydantic import SecretStr, ValidationError

VALID_DATABASE_URL = "postgresql+asyncpg://user:secret@localhost:5432/bff"
VALID_MIGRATION_DATABASE_URL = "postgresql+psycopg://user:secret@localhost:5432/bff"


def make_settings(
    *,
    database_url: str = VALID_DATABASE_URL,
    migration_database_url: str = VALID_MIGRATION_DATABASE_URL,
) -> DatabaseSettings:
    return DatabaseSettings(
        database_url=SecretStr(database_url),
        migration_database_url=SecretStr(migration_database_url),
    )


def test_database_urls_require_explicit_runtime_and_migration_drivers() -> None:
    settings = make_settings()

    assert settings.database_url.get_secret_value().startswith(
        "postgresql+asyncpg://",
    )
    assert settings.migration_database_url.get_secret_value().startswith(
        "postgresql+psycopg://",
    )


@pytest.mark.parametrize(
    ("database_url", "migration_database_url"),
    [
        (
            "postgresql+psycopg://user:secret@localhost/bff",
            VALID_MIGRATION_DATABASE_URL,
        ),
        (
            VALID_DATABASE_URL,
            "postgresql+asyncpg://user:secret@localhost/bff",
        ),
    ],
)
def test_database_urls_reject_wrong_driver(
    database_url: str,
    migration_database_url: str,
) -> None:
    with pytest.raises(ValidationError):
        make_settings(
            database_url=database_url,
            migration_database_url=migration_database_url,
        )


def test_database_settings_repr_redacts_passwords() -> None:
    settings = make_settings(
        database_url=("postgresql+asyncpg://user:super-secret@localhost/bff"),
        migration_database_url=("postgresql+psycopg://user:other-secret@localhost/bff"),
    )

    representation = repr(settings)

    assert "super-secret" not in representation
    assert "other-secret" not in representation
