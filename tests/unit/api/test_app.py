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
    def __init__(
        self,
        *,
        principal: AuthenticatedPrincipal | None,
    ) -> None:
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
) -> Generator[tuple[TestClient, FakeDatabase, FakeTelemetry, FakeAuthenticator],]:
    database = FakeDatabase(ready=ready)
    telemetry = FakeTelemetry()
    authenticator = FakeAuthenticator(principal=principal)
    resources = ApplicationResources(
        database=database,
        telemetry=telemetry,
        authenticator=authenticator,
    )
    app = create_app(resource_factory=lambda: resources)

    with TestClient(app) as client:
        yield client, database, telemetry, authenticator

    assert database.disposed
    assert telemetry.shutdown_called


def test_liveness_does_not_depend_on_database_readiness() -> None:
    with client_for(ready=False) as (client, _, _, _):
        response = client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ready_when_database_is_available() -> None:
    with client_for(ready=True) as (client, _, _, _):
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_returns_503_when_database_is_unavailable() -> None:
    with client_for(ready=False) as (client, _, _, _):
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_me_requires_bearer_authentication() -> None:
    with client_for(ready=True, principal=_principal()) as (
        client,
        _,
        _,
        authenticator,
    ):
        response = client.get("/v1/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid authentication credentials"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert authenticator.tokens == []


def test_me_normalizes_invalid_or_unadmitted_credentials() -> None:
    with client_for(ready=True, principal=None) as (
        client,
        _,
        _,
        authenticator,
    ):
        response = client.get(
            "/v1/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid authentication credentials"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert authenticator.tokens == ["invalid-token"]


def test_me_returns_only_public_bff_user_fields() -> None:
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


def test_openapi_contains_foundation_and_authenticated_identity_routes() -> None:
    database = FakeDatabase(ready=True)
    telemetry = FakeTelemetry()
    authenticator = FakeAuthenticator(principal=_principal())
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=database,
            telemetry=telemetry,
            authenticator=authenticator,
        )
    )
    schema = app.openapi()

    assert sorted(schema["paths"]) == ["/livez", "/readyz", "/v1/me"]
    assert schema["paths"]["/livez"]["get"]["operationId"] == "livez"
    assert schema["paths"]["/readyz"]["get"]["operationId"] == "readyz"
    assert schema["paths"]["/v1/me"]["get"]["operationId"] == "getMe"
    assert schema["paths"]["/v1/me"]["get"]["security"] == [{"HTTPBearer": []}]
