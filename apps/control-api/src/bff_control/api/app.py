"""FastAPI application factory and process lifecycle."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from bff_control.api.contracts import ApplicationResources
from bff_control.api.middleware.request_context import RequestContextMiddleware
from bff_control.api.problems.handlers import register_problem_handlers
from bff_control.api.problems.openapi import ControlApi
from bff_control.api.routes.health import router as health_router
from bff_control.api.routes.v1.auth import router as auth_router
from bff_control.api.routes.v1.identity import router as identity_router
from bff_control.api.routes.v1.workspaces import router as workspaces_router

ResourceFactory = Callable[[], ApplicationResources]


def create_app(*, resource_factory: ResourceFactory) -> ControlApi:
    @asynccontextmanager
    async def lifespan(app: ControlApi) -> AsyncGenerator[None]:
        resources = resource_factory()
        app.state.database = resources.database
        app.state.telemetry = resources.telemetry
        app.state.authenticator = resources.authenticator
        app.state.session_provisioner = resources.session_provisioner
        app.state.workspace_service = resources.workspace_service
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

    app = ControlApi(
        title="Backend for Framer Control API",
        version="0.0.0",
        lifespan=lifespan,
    )
    register_problem_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(identity_router)
    app.include_router(workspaces_router)
    return app
