from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from bff_control.api.app import create_app
from fastapi.testclient import TestClient
from opentelemetry import trace


class FakeDatabase:
    def __init__(self, *, ready: bool) -> None:
        self.ready = ready
        self.disposed = False

    async def is_ready(self) -> bool:
        return self.ready

    async def dispose(self) -> None:
        self.disposed = True


class FakeTelemetry:
    def __init__(self) -> None:
        self.tracer = trace.NoOpTracerProvider().get_tracer("test")
        self.shutdown_called = False

    def shutdown(self) -> None:
        self.shutdown_called = True


@contextmanager
def client_for(
    *,
    ready: bool,
) -> Generator[tuple[TestClient, FakeDatabase, FakeTelemetry]]:
    database = FakeDatabase(ready=ready)
    telemetry = FakeTelemetry()
    app = create_app(
        database_factory=lambda: database,
        telemetry_factory=lambda: telemetry,
    )

    with TestClient(app) as client:
        yield client, database, telemetry

    assert database.disposed
    assert telemetry.shutdown_called


def test_liveness_does_not_depend_on_database_readiness() -> None:
    with client_for(ready=False) as (client, _, _):
        response = client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ready_when_database_is_available() -> None:
    with client_for(ready=True) as (client, _, _):
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_returns_503_when_database_is_unavailable() -> None:
    with client_for(ready=False) as (client, _, _):
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_openapi_contains_only_foundation_routes() -> None:
    database = FakeDatabase(ready=True)
    telemetry = FakeTelemetry()
    app = create_app(
        database_factory=lambda: database,
        telemetry_factory=lambda: telemetry,
    )
    schema = app.openapi()

    assert sorted(schema["paths"]) == ["/livez", "/readyz"]
    assert schema["paths"]["/livez"]["get"]["operationId"] == "livez"
    assert schema["paths"]["/readyz"]["get"]["operationId"] == "readyz"
