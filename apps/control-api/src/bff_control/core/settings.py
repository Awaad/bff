"""Control-plane environment settings.

Secrets are represented as SecretStr so accidental repr/logging does not expose
database credentials.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ASYNC_DRIVER = "postgresql+asyncpg"
MIGRATION_DRIVER = "postgresql+psycopg"


class ApplicationSettings(BaseSettings):
    """Process-level control API settings that are safe to expose internally."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BFF_",
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str = "bff-control"
    environment: str = "dev"
    telemetry_enabled: bool = False
    otel_traces_endpoint: AnyHttpUrl = AnyHttpUrl(
        "http://127.0.0.1:4318/v1/traces",
    )


@lru_cache(maxsize=1)
def get_application_settings() -> ApplicationSettings:
    """Return process-wide validated application settings."""

    return ApplicationSettings()


class DatabaseSettings(BaseSettings):
    """Database settings shared by application runtime and migration tooling."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BFF_",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: SecretStr
    migration_database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        driver = make_url(value.get_secret_value()).drivername
        if driver != ASYNC_DRIVER:
            msg = f"database_url must use {ASYNC_DRIVER}; got {driver}"
            raise ValueError(msg)
        return value

    @field_validator("migration_database_url")
    @classmethod
    def validate_migration_database_url(cls, value: SecretStr) -> SecretStr:
        driver = make_url(value.get_secret_value()).drivername
        if driver != MIGRATION_DRIVER:
            msg = f"migration_database_url must use {MIGRATION_DRIVER}; got {driver}"
            raise ValueError(msg)
        return value


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """Return process-wide validated database settings."""

    return DatabaseSettings()
