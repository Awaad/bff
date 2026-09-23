from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from bff_control.api.app import create_app
from bff_control.api.contracts import ApplicationResources
from bff_control.domains.authentication.contracts import PrincipalAuthenticationError
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from bff_control.domains.projects.contracts import (
    ProjectNotFoundError,
    ProjectPermissionDeniedError,
    ProjectWorkspaceNotActiveError,
    ProjectWorkspaceNotFoundError,
)
from bff_control.domains.projects.models import (
    Project,
    ProjectPage,
    ProjectPageCursor,
    ProjectStatus,
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


class FakeProjectManager:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.create_error: Exception | None = None
        self.list_calls: list[dict[str, object]] = []
        self.list_error: Exception | None = None
        self.page = ProjectPage(items=(), next_cursor=None)
        self.get_error: Exception | None = None
        self.get_result = _project()

    async def create_project(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> Project:
        if self.create_error is not None:
            raise self.create_error
        self.created = {
            "user_id": user_id,
            "auth_session_id": auth_session_id,
            "workspace_id": workspace_id,
            "name": name,
            "request_id": request_id,
            "trace_id": trace_id,
        }
        return _project(name=name)

    async def list_projects(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ProjectPageCursor | None,
        limit: int,
    ) -> ProjectPage:
        if self.list_error is not None:
            raise self.list_error
        self.list_calls.append(
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "cursor": cursor,
                "limit": limit,
            }
        )
        return self.page

    async def get_project(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        project_id: UUID,
    ) -> Project:
        del user_id, workspace_id, project_id
        if self.get_error is not None:
            raise self.get_error
        return self.get_result


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=UUID("00000000-0000-7000-8000-000000000931"),
        auth_session_id=UUID("00000000-0000-7000-8000-000000000932"),
        email="project-user@example.test",
        display_name="Project User",
    )


def _project(*, name: str = "Project One") -> Project:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    return Project(
        project_id=UUID("00000000-0000-7000-8000-000000000933"),
        workspace_id=UUID("00000000-0000-7000-8000-000000000934"),
        name=name,
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        archived_at=None,
    )


@contextmanager
def _client(
    *,
    principal: AuthenticatedPrincipal | None = None,
    manager: FakeProjectManager | None = None,
) -> Generator[tuple[TestClient, FakeProjectManager]]:
    project_manager = manager or FakeProjectManager()
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=FakeAuthenticator(principal),
            project_service=project_manager,
        )
    )
    with TestClient(app) as client:
        yield client, project_manager


def _collection_path() -> str:
    return "/v1/workspaces/00000000-0000-7000-8000-000000000934/projects"


def test_project_routes_require_bearer_authentication() -> None:
    with _client(principal=_principal()) as (client, _):
        response = client.get(_collection_path())

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"


def test_create_project_returns_location_and_forwards_request_context() -> None:
    with _client(principal=_principal()) as (client, manager):
        response = client.post(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
            json={"name": "  Project One  "},
        )

    assert response.status_code == 201
    assert response.headers["location"].endswith("/projects/00000000-0000-7000-8000-000000000933")
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["name"] == "Project One"
    assert manager.created is not None
    assert manager.created["name"] == "Project One"
    assert str(manager.created["request_id"]) == response.headers["x-request-id"]


def test_create_project_uses_structured_validation_problem() -> None:
    with _client(principal=_principal()) as (client, manager):
        response = client.post(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
            json={"name": "   "},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"
    assert response.json()["errors"][0]["pointer"] == "#/body/name"
    assert manager.created is None


def test_create_project_maps_permission_and_lifecycle_failures() -> None:
    manager = FakeProjectManager()
    manager.create_error = ProjectPermissionDeniedError("denied")
    with _client(principal=_principal(), manager=manager) as (client, _):
        denied = client.post(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
            json={"name": "Denied"},
        )

    manager.create_error = ProjectWorkspaceNotActiveError("inactive")
    with _client(principal=_principal(), manager=manager) as (client, _):
        inactive = client.post(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
            json={"name": "Inactive"},
        )

    assert denied.status_code == 403
    assert denied.json()["code"] == "WORKSPACE_PERMISSION_DENIED"
    assert inactive.status_code == 409
    assert inactive.json()["code"] == "WORKSPACE_NOT_ACTIVE"


def test_project_list_cursor_round_trips_as_opaque_token() -> None:
    manager = FakeProjectManager()
    project = _project()
    manager.page = ProjectPage(
        items=(project,),
        next_cursor=ProjectPageCursor(
            created_at=project.created_at,
            project_id=project.project_id,
        ),
    )

    with _client(principal=_principal(), manager=manager) as (client, _):
        first = client.get(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
            params={"limit": 1},
        )
        cursor = first.json()["next_cursor"]
        second = client.get(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
            params={"limit": 1, "cursor": cursor},
        )

    assert first.status_code == 200
    assert cursor is not None
    assert second.status_code == 200
    assert manager.list_calls[0]["cursor"] is None
    assert manager.list_calls[1]["cursor"] == manager.page.next_cursor


def test_project_list_rejects_invalid_cursor_and_limit() -> None:
    with _client(principal=_principal()) as (client, manager):
        invalid_cursor = client.get(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
            params={"cursor": "not-a-cursor"},
        )
        invalid_limit = client.get(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
            params={"limit": 101},
        )

    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["code"] == "REQUEST_VALIDATION_FAILED"
    assert invalid_cursor.json()["errors"][0]["pointer"] == "#/query/cursor"
    assert invalid_limit.status_code == 422
    assert invalid_limit.json()["code"] == "REQUEST_VALIDATION_FAILED"
    assert manager.list_calls == []


def test_project_reads_map_workspace_and_project_existence_hiding() -> None:
    manager = FakeProjectManager()
    manager.list_error = ProjectWorkspaceNotFoundError("workspace not found")
    with _client(principal=_principal(), manager=manager) as (client, _):
        workspace_missing = client.get(
            _collection_path(),
            headers={"Authorization": "Bearer valid-token"},
        )

    manager.get_error = ProjectNotFoundError("project not found")
    with _client(principal=_principal(), manager=manager) as (client, _):
        project_missing = client.get(
            f"{_collection_path()}/00000000-0000-7000-8000-000000000999",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert workspace_missing.status_code == 404
    assert workspace_missing.json()["code"] == "WORKSPACE_NOT_FOUND"
    assert project_missing.status_code == 404
    assert project_missing.json()["code"] == "PROJECT_NOT_FOUND"


def test_project_openapi_publishes_bounded_list_and_stable_problems() -> None:
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=FakeAuthenticator(_principal()),
            project_service=FakeProjectManager(),
        )
    )

    schema = app.openapi()
    path = schema["paths"]["/v1/workspaces/{workspace_id}/projects"]
    parameters = {item["name"]: item for item in path["get"]["parameters"]}
    problem_codes = schema["components"]["schemas"]["ProblemCode"]["enum"]

    assert path["post"]["operationId"] == "createProject"
    assert path["get"]["operationId"] == "listProjects"
    assert parameters["limit"]["schema"]["default"] == 50
    assert parameters["limit"]["schema"]["maximum"] == 100
    assert parameters["cursor"]["schema"]["anyOf"][0]["maxLength"] == 512
    assert "PROJECT_NOT_FOUND" in problem_codes
    assert "WORKSPACE_PERMISSION_DENIED" in problem_codes
    assert "WORKSPACE_NOT_ACTIVE" in problem_codes
