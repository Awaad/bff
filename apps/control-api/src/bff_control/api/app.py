"""FastAPI application factory and process lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bff_control.api.contracts import DatabaseLifecycle, TelemetryLifecycle
from bff_control.api.health import router as health_router

DatabaseFactory = Callable[[], DatabaseLifecycle]
TelemetryFactory = Callable[[], TelemetryLifecycle]


def create_app(
    *,
    database_factory: DatabaseFactory,
    telemetry_factory: TelemetryFactory,
) -> FastAPI:
    """Create the control API with explicitly supplied process resources."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = database_factory()
        telemetry = telemetry_factory()

        app.state.database = database
        app.state.telemetry = telemetry

        with telemetry.tracer.start_as_current_span("control_api.startup"):
            pass

        try:
            yield
        finally:
            try:
                await database.dispose()
            finally:
                with telemetry.tracer.start_as_current_span("control_api.shutdown"):
                    pass
                telemetry.shutdown()

    app = FastAPI(
        title="Backend for Framer Control API",
        version="0.0.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    return app
