from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from bff_control.api.app import create_app
from bff_control.api.contracts import ApplicationResources
from bff_control.domains.authentication.contracts import PrincipalAuthenticationError
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from bff_control.domains.workspaces.contracts import WorkspaceNotFoundError
from bff_control.domains.workspaces.models import (
    WorkspaceAccess,
    WorkspaceRole,
    WorkspaceStatus,
)
from fastapi.testclient import TestClient
from opentelemetry import trace


class FakeDatabase:
    async def is_ready(self) -> bool:
        return True

    async def dispose(self) -> None:
        return None


class FakeTelemetry:
    def __init__(self) -> None:
        self.tracer = trace.NoOpTracerProvider().get_tracer("test")

    def shutdown(self) -> None:
        return None


class FakeAuthenticator:
    def __init__(self, principal: AuthenticatedPrincipal | None) -> None:
        self.principal = principal

    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        del token
        if self.principal is None:
            raise PrincipalAuthenticationError("authentication failed")
        return self.principal


class FakeWorkspaceManager:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.items: tuple[WorkspaceAccess, ...] = ()
        self.get_result: WorkspaceAccess | None = None

    async def create_workspace(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> WorkspaceAccess:
        self.created = {
            "user_id": user_id,
            "auth_session_id": auth_session_id,
            "name": name,
            "request_id": request_id,
            "trace_id": trace_id,
        }
        return _access()

    async def list_workspaces(self, user_id: UUID) -> tuple[WorkspaceAccess, ...]:
        del user_id
        return self.items

    async def get_workspace(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
    ) -> WorkspaceAccess:
        del user_id, workspace_id
        if self.get_result is None:
            raise WorkspaceNotFoundError("workspace not found")
        return self.get_result


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=UUID("00000000-0000-7000-8000-000000000721"),
        auth_session_id=UUID("00000000-0000-7000-8000-000000000722"),
        email="workspace-user@example.test",
        display_name="Workspace User",
    )


def _access(
    *,
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
    role: WorkspaceRole = WorkspaceRole.OWNER,
) -> WorkspaceAccess:
    now = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    return WorkspaceAccess(
        workspace_id=UUID("00000000-0000-7000-8000-000000000723"),
        name="Workspace One",
        status=status,
        role=role,
        created_at=now,
        updated_at=now,
    )


@contextmanager
def _client(
    *,
    principal: AuthenticatedPrincipal | None = None,
    manager: FakeWorkspaceManager | None = None,
) -> Generator[tuple[TestClient, FakeWorkspaceManager]]:
    workspace_manager = manager or FakeWorkspaceManager()
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=FakeAuthenticator(principal),
            workspace_service=workspace_manager,
        )
    )
    with TestClient(app) as client:
        yield client, workspace_manager


def test_workspace_routes_require_bearer_authentication() -> None:
    with _client(principal=_principal()) as (client, _):
        response = client.get("/v1/workspaces")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert response.headers["www-authenticate"] == "Bearer"


def test_create_workspace_returns_owner_and_forwards_request_context() -> None:
    with _client(principal=_principal()) as (client, manager):
        response = client.post(
            "/v1/workspaces",
            headers={"Authorization": "Bearer valid-token"},
            json={"name": "  Workspace One  "},
        )

    assert response.status_code == 201
    assert response.headers["location"] == ("/v1/workspaces/00000000-0000-7000-8000-000000000723")
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["role"] == "OWNER"
    assert response.json()["status"] == "ACTIVE"
    assert manager.created is not None
    assert manager.created["name"] == "Workspace One"
    assert str(manager.created["request_id"]) == response.headers["x-request-id"]


def test_create_workspace_uses_structured_validation_problem() -> None:
    with _client(principal=_principal()) as (client, manager):
        response = client.post(
            "/v1/workspaces",
            headers={"Authorization": "Bearer valid-token"},
            json={"name": "   "},
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"
    assert response.json()["errors"][0]["pointer"] == "#/body/name"
    assert manager.created is None


def test_list_workspaces_returns_membership_role_and_lifecycle_state() -> None:
    manager = FakeWorkspaceManager()
    manager.items = (_access(status=WorkspaceStatus.SUSPENDED, role=WorkspaceRole.VIEWER),)

    with _client(principal=_principal(), manager=manager) as (client, _):
        response = client.get(
            "/v1/workspaces",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["items"][0]["status"] == "SUSPENDED"
    assert response.json()["items"][0]["role"] == "VIEWER"


def test_get_workspace_hides_nonmembership_as_workspace_not_found() -> None:
    with _client(principal=_principal()) as (client, _):
        response = client.get(
            "/v1/workspaces/00000000-0000-7000-8000-000000000799",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "WORKSPACE_NOT_FOUND"


def test_workspace_openapi_normalizes_validation_and_problem_contracts() -> None:
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=FakeAuthenticator(_principal()),
            workspace_service=FakeWorkspaceManager(),
        )
    )

    schema = app.openapi()
    schemas = schema["components"]["schemas"]
    create_responses = schema["paths"]["/v1/workspaces"]["post"]["responses"]
    get_responses = schema["paths"]["/v1/workspaces/{workspace_id}"]["get"]["responses"]

    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas
    assert schemas["CreateWorkspaceRequest"]["properties"]["name"]["maxLength"] == 120
    assert create_responses["201"]["headers"]["Location"]["schema"] == {"type": "string"}
    assert "application/problem+json" in create_responses["422"]["content"]
    assert get_responses["404"]["description"] == "Workspace not found"
    assert "WORKSPACE_NOT_FOUND" in schemas["ProblemCode"]["enum"]
