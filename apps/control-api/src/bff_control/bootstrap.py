"""Control-plane composition root."""

from fastapi import FastAPI

from bff_control.api.app import create_app
from bff_control.api.contracts import DatabaseLifecycle, TelemetryLifecycle
from bff_control.core.settings import get_application_settings, get_database_settings
from bff_control.infrastructure.db.database import Database
from bff_control.infrastructure.observability.telemetry import configure_telemetry


def _database_factory() -> DatabaseLifecycle:
    return Database(get_database_settings())


def _telemetry_factory() -> TelemetryLifecycle:
    return configure_telemetry(get_application_settings())


def create_application() -> FastAPI:
    """Wire the HTTP transport to concrete process infrastructure."""

    return create_app(
        database_factory=_database_factory,
        telemetry_factory=_telemetry_factory,
    )
