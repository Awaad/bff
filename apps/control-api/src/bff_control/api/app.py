"""FastAPI application factory and process lifecycle."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bff_control.api.contracts import ApplicationResources
from bff_control.api.health import router as health_router
from bff_control.api.me import router as me_router

ResourceFactory = Callable[[], ApplicationResources]


def create_app(*, resource_factory: ResourceFactory) -> FastAPI:
    """Create the control API with explicitly supplied process resources."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        resources = resource_factory()

        app.state.database = resources.database
        app.state.telemetry = resources.telemetry
        app.state.authenticator = resources.authenticator

        with resources.telemetry.tracer.start_as_current_span("control_api.startup"):
            pass

        try:
            yield
        finally:
            try:
                await resources.database.dispose()
            finally:
                with resources.telemetry.tracer.start_as_current_span(
                    "control_api.shutdown",
                ):
                    pass
                resources.telemetry.shutdown()

    app = FastAPI(
        title="Backend for Framer Control API",
        version="0.0.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(me_router)
    return app
