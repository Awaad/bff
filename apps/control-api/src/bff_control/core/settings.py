"""Control-plane environment settings.

Secrets are represented as SecretStr so accidental repr/logging does not expose
database credentials.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_validator,
)
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


class AuthenticationSettings(BaseSettings):
    """Trusted external-authentication verification configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BFF_AUTH_",
        extra="ignore",
        case_sensitive=False,
    )

    issuer: str
    client_id: str
    jwks_url: AnyHttpUrl
    jwks_cache_ttl_seconds: PositiveFloat = 300.0
    jwks_request_timeout_seconds: PositiveFloat = 5.0
    jwks_unknown_kid_cooldown_seconds: NonNegativeFloat = 30.0
    jwt_leeway_seconds: NonNegativeInt = 30
    max_bearer_token_length: PositiveInt = 16_384
    session_absolute_ttl_seconds: PositiveInt = 604_800

    @field_validator("issuer")
    @classmethod
    def validate_issuer(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "issuer must be a non-empty exact URL without surrounding whitespace"
            )

        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "issuer must be an HTTPS origin/path without credentials/query/fragment",
            )

        return value

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("client_id must be non-empty without surrounding whitespace")
        return value

    @field_validator("jwks_url")
    @classmethod
    def validate_jwks_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("jwks_url must use HTTPS")
        return value


@lru_cache(maxsize=1)
def get_authentication_settings() -> AuthenticationSettings:
    """Return process-wide validated authentication settings."""

    return AuthenticationSettings()


class WorkOSSettings(BaseSettings):
    """Server-side WorkOS User Management API configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BFF_WORKOS_",
        extra="ignore",
        case_sensitive=False,
    )

    api_key: SecretStr
    api_base_url: AnyHttpUrl = AnyHttpUrl("https://api.workos.com")
    user_request_timeout_seconds: PositiveFloat = 5.0

    @field_validator("api_base_url")
    @classmethod
    def validate_api_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("WorkOS api_base_url must use HTTPS")
        return value


@lru_cache(maxsize=1)
def get_workos_settings() -> WorkOSSettings:
    """Return process-wide validated WorkOS management settings."""

    return WorkOSSettings()


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
