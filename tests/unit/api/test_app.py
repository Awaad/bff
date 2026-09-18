from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID

from bff_control.api.app import create_app
from bff_control.api.contracts import ApplicationResources
from bff_control.domains.authentication.contracts import PrincipalAuthenticationError
from bff_control.domains.authentication.models import AuthenticatedPrincipal
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


class FakeAuthenticator:
    def __init__(self, *, principal: AuthenticatedPrincipal | None) -> None:
        self.principal = principal
        self.tokens: list[str] = []

    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        self.tokens.append(token)
        if self.principal is None:
            raise PrincipalAuthenticationError("authentication failed")
        return self.principal


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=UUID("00000000-0000-7000-8000-000000000601"),
        auth_session_id=UUID("00000000-0000-7000-8000-000000000602"),
        email="current@example.test",
        display_name="Current User",
    )


@contextmanager
def client_for(
    *,
    ready: bool,
    principal: AuthenticatedPrincipal | None = None,
) -> Generator[tuple[TestClient, FakeDatabase, FakeTelemetry, FakeAuthenticator]]:
    database = FakeDatabase(ready=ready)
    telemetry = FakeTelemetry()
    authenticator = FakeAuthenticator(principal=principal)
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=database,
            telemetry=telemetry,
            authenticator=authenticator,
        )
    )
    with TestClient(app) as client:
        yield client, database, telemetry, authenticator
    assert database.disposed
    assert telemetry.shutdown_called


def test_liveness_has_request_id() -> None:
    with client_for(ready=False) as (client, _, _, _):
        response = client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_readiness_statuses() -> None:
    with client_for(ready=True) as (client, _, _, _):
        assert client.get("/readyz").status_code == 200
    with client_for(ready=False) as (client, _, _, _):
        assert client.get("/readyz").status_code == 503


def test_me_requires_structured_bearer_authentication() -> None:
    with client_for(ready=True, principal=_principal()) as (
        client,
        _,
        _,
        authenticator,
    ):
        response = client.get("/v1/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert authenticator.tokens == []


def test_me_returns_public_user_fields() -> None:
    with client_for(ready=True, principal=_principal()) as (
        client,
        _,
        _,
        authenticator,
    ):
        response = client.get(
            "/v1/me",
            headers={"Authorization": "Bearer valid-token"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "id": "00000000-0000-7000-8000-000000000601",
        "email": "current@example.test",
        "display_name": "Current User",
    }
    assert response.headers["cache-control"] == "no-store"
    assert authenticator.tokens == ["valid-token"]
