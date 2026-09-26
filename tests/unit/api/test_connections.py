from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from bff_control.api.app import create_app
from bff_control.api.contracts import ApplicationResources
from bff_control.domains.authentication.contracts import PrincipalAuthenticationError
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from bff_control.domains.connections.contracts import (
    ConnectionConfigurationInvalidError,
    ConnectionNotFoundError,
    ConnectionPermissionDeniedError,
    ConnectionProjectNotFoundError,
    ConnectionStateConflictError,
    ConnectionWorkspaceNotActiveError,
)
from bff_control.domains.connections.models import (
    Connection,
    ConnectionAccessMode,
    ConnectionAccessPolicy,
    ConnectionDraft,
    ConnectionLifecycleAction,
    ConnectionPage,
    ConnectionPageCursor,
    ConnectionRevision,
    ConnectionRevisionMetadata,
    ConnectionRevisionPage,
    ConnectionStatus,
)
from fastapi.testclient import TestClient
from opentelemetry import trace

USER_ID = UUID("00000000-0000-7000-8000-000000002101")
SESSION_ID = UUID("00000000-0000-7000-8000-000000002102")
WORKSPACE_ID = UUID("00000000-0000-7000-8000-000000002103")
CONNECTION_ID = UUID("00000000-0000-7000-8000-000000002104")
PROJECT_ID = UUID("00000000-0000-7000-8000-000000002105")
REVISION_ID = UUID("00000000-0000-7000-8000-000000002106")
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


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


class FakeConnectionManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.error: Exception | None = None
        self.connection = _connection()
        self.page = ConnectionPage(items=(self.connection,), next_cursor=None)

    def _record(self, operation: str, values: dict[str, object]) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append((operation, values))

    async def create_connection(self, **kwargs: object) -> Connection:
        self._record("create", kwargs)
        return self.connection

    async def list_connections(self, **kwargs: object) -> ConnectionPage:
        self._record("list", kwargs)
        return self.page

    async def get_connection(self, **kwargs: object) -> Connection:
        self._record("get", kwargs)
        return self.connection

    async def rename_connection(self, **kwargs: object) -> Connection:
        self._record("rename", kwargs)
        return self.connection

    async def get_draft(self, **kwargs: object) -> ConnectionDraft:
        self._record("get_draft", kwargs)
        return _draft()

    async def put_draft(
        self,
        *,
        configuration: Mapping[str, object],
        **kwargs: object,
    ) -> ConnectionDraft:
        self._record("put_draft", {**kwargs, "configuration": dict(configuration)})
        return _draft()

    async def list_revisions(self, **kwargs: object) -> ConnectionRevisionPage:
        self._record("list_revisions", kwargs)
        return ConnectionRevisionPage(
            items=(_revision().metadata,),
            next_before_revision=1,
        )

    async def get_revision(self, **kwargs: object) -> ConnectionRevision:
        self._record("get_revision", kwargs)
        return _revision()

    async def publish_revision(self, **kwargs: object) -> ConnectionRevision:
        self._record("publish_revision", kwargs)
        return _revision()

    async def replace_access(self, **kwargs: object) -> Connection:
        self._record("replace_access", kwargs)
        return self.connection

    async def transition_lifecycle(self, **kwargs: object) -> Connection:
        self._record("lifecycle", kwargs)
        return self.connection


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=USER_ID,
        auth_session_id=SESSION_ID,
        email="connection-user@example.test",
        display_name="Connection User",
    )


def _connection() -> Connection:
    return Connection(
        connection_id=CONNECTION_ID,
        workspace_id=WORKSPACE_ID,
        name="Primary API",
        provider_key="generic_http",
        access_policy=ConnectionAccessPolicy(
            mode=ConnectionAccessMode.SELECTED_PROJECTS,
            project_ids=(PROJECT_ID,),
        ),
        status=ConnectionStatus.DRAFT,
        created_at=NOW,
        updated_at=NOW,
        archived_at=None,
    )


def _draft() -> ConnectionDraft:
    return ConnectionDraft(
        connection_id=CONNECTION_ID,
        workspace_id=WORKSPACE_ID,
        configuration={"base_url": "https://api.example.com"},
        updated_by_user_id=USER_ID,
        updated_at=NOW,
    )


def _revision() -> ConnectionRevision:
    return ConnectionRevision(
        metadata=ConnectionRevisionMetadata(
            revision_id=REVISION_ID,
            connection_id=CONNECTION_ID,
            workspace_id=WORKSPACE_ID,
            revision_number=1,
            definition_schema_version=1,
            config_hash_hex="ab" * 32,
            created_by_user_id=USER_ID,
            created_at=NOW,
        ),
        configuration={"base_url": "https://api.example.com"},
    )


@contextmanager
def _client(
    *,
    principal: AuthenticatedPrincipal | None = None,
    manager: FakeConnectionManager | None = None,
) -> Generator[tuple[TestClient, FakeConnectionManager]]:
    connection_manager = manager or FakeConnectionManager()
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=FakeAuthenticator(principal),
            connection_service=connection_manager,
        )
    )
    with TestClient(app) as client:
        yield client, connection_manager


def _collection_path() -> str:
    return f"/v1/workspaces/{WORKSPACE_ID}/connections"


def _connection_path() -> str:
    return f"{_collection_path()}/{CONNECTION_ID}"


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer valid-token"}


def test_connection_routes_require_bearer_authentication() -> None:
    with _client(principal=_principal()) as (client, _):
        response = client.get(_collection_path())

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"


def test_create_connection_forwards_explicit_access_and_request_context() -> None:
    with _client(principal=_principal()) as (client, manager):
        response = client.post(
            _collection_path(),
            headers=_auth(),
            json={
                "name": "  Primary API  ",
                "provider_key": "generic_http",
                "access": {
                    "mode": "SELECTED_PROJECTS",
                    "project_ids": [str(PROJECT_ID)],
                },
            },
        )

    assert response.status_code == 201
    assert response.headers["location"] == _connection_path()
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["access"]["project_ids"] == [str(PROJECT_ID)]
    operation, values = manager.calls[0]
    assert operation == "create"
    assert values["name"] == "Primary API"
    assert str(values["request_id"]) == response.headers["x-request-id"]


def test_connection_access_request_rejects_inconsistent_or_duplicate_projects() -> None:
    with _client(principal=_principal()) as (client, manager):
        workspace_with_projects = client.post(
            _collection_path(),
            headers=_auth(),
            json={
                "name": "Primary API",
                "provider_key": "generic_http",
                "access": {
                    "mode": "WORKSPACE",
                    "project_ids": [str(PROJECT_ID)],
                },
            },
        )
        duplicate = client.put(
            f"{_connection_path()}/access",
            headers=_auth(),
            json={
                "mode": "SELECTED_PROJECTS",
                "project_ids": [str(PROJECT_ID), str(PROJECT_ID)],
            },
        )

    assert workspace_with_projects.status_code == 422
    assert duplicate.status_code == 422
    assert manager.calls == []


def test_connection_list_cursor_round_trips() -> None:
    manager = FakeConnectionManager()
    manager.page = ConnectionPage(
        items=(manager.connection,),
        next_cursor=ConnectionPageCursor(
            created_at=NOW,
            connection_id=CONNECTION_ID,
        ),
    )
    with _client(principal=_principal(), manager=manager) as (client, _):
        first = client.get(_collection_path(), headers=_auth(), params={"limit": 1})
        second = client.get(
            _collection_path(),
            headers=_auth(),
            params={"limit": 1, "cursor": first.json()["next_cursor"]},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert manager.calls[0][1]["cursor"] is None
    assert manager.calls[1][1]["cursor"] == manager.page.next_cursor


def test_draft_and_revision_routes_keep_configuration_on_authoring_surface() -> None:
    with _client(principal=_principal()) as (client, manager):
        detail = client.get(_connection_path(), headers=_auth())
        put_draft = client.put(
            f"{_connection_path()}/draft",
            headers=_auth(),
            json={"configuration": {"base_url": "https://api.example.com"}},
        )
        publish = client.post(f"{_connection_path()}/revisions", headers=_auth())
        revision = client.get(
            f"{_connection_path()}/revisions/{REVISION_ID}",
            headers=_auth(),
        )

    assert detail.status_code == 200
    assert "configuration" not in detail.json()
    assert put_draft.json()["configuration"]["base_url"] == "https://api.example.com"
    assert publish.status_code == 201
    assert publish.headers["location"].endswith(f"/revisions/{REVISION_ID}")
    assert revision.json()["configuration"]["base_url"] == "https://api.example.com"
    assert [item[0] for item in manager.calls] == [
        "get",
        "put_draft",
        "publish_revision",
        "get_revision",
    ]


def test_revision_list_uses_bounded_revision_number_cursor() -> None:
    with _client(principal=_principal()) as (client, manager):
        response = client.get(
            f"{_connection_path()}/revisions",
            headers=_auth(),
            params={"before_revision": 12, "limit": 5},
        )

    assert response.status_code == 200
    assert response.json()["next_before_revision"] == 1
    assert manager.calls == [
        (
            "list_revisions",
            {
                "user_id": USER_ID,
                "workspace_id": WORKSPACE_ID,
                "connection_id": CONNECTION_ID,
                "before_revision": 12,
                "limit": 5,
            },
        )
    ]


def test_lifecycle_custom_methods_route_to_explicit_actions() -> None:
    with _client(principal=_principal()) as (client, manager):
        disabled = client.post(f"{_connection_path()}:disable", headers=_auth())
        enabled = client.post(f"{_connection_path()}:enable", headers=_auth())
        archived = client.post(f"{_connection_path()}:archive", headers=_auth())

    assert disabled.status_code == 200
    assert enabled.status_code == 200
    assert archived.status_code == 200
    assert [item[1]["action"] for item in manager.calls] == [
        ConnectionLifecycleAction.DISABLE,
        ConnectionLifecycleAction.ENABLE,
        ConnectionLifecycleAction.ARCHIVE,
    ]


def test_connection_domain_failures_map_to_stable_problems() -> None:
    cases = [
        (ConnectionNotFoundError("missing"), 404, "CONNECTION_NOT_FOUND"),
        (ConnectionProjectNotFoundError("missing"), 404, "PROJECT_NOT_FOUND"),
        (
            ConnectionPermissionDeniedError("denied"),
            403,
            "WORKSPACE_PERMISSION_DENIED",
        ),
        (
            ConnectionWorkspaceNotActiveError("inactive"),
            409,
            "WORKSPACE_NOT_ACTIVE",
        ),
        (
            ConnectionStateConflictError("conflict"),
            409,
            "CONNECTION_STATE_CONFLICT",
        ),
        (
            ConnectionConfigurationInvalidError("invalid"),
            422,
            "REQUEST_VALIDATION_FAILED",
        ),
    ]

    for error, expected_status, expected_code in cases:
        manager = FakeConnectionManager()
        manager.error = error
        with _client(principal=_principal(), manager=manager) as (client, _):
            response = client.get(_connection_path(), headers=_auth())
        assert response.status_code == expected_status
        assert response.json()["code"] == expected_code


def test_connection_openapi_publishes_complete_surface_and_stable_problems() -> None:
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=FakeAuthenticator(_principal()),
            connection_service=FakeConnectionManager(),
        )
    )
    schema = app.openapi()
    collection = schema["paths"]["/v1/workspaces/{workspace_id}/connections"]
    detail = schema["paths"]["/v1/workspaces/{workspace_id}/connections/{connection_id}"]
    revisions = schema["paths"][
        "/v1/workspaces/{workspace_id}/connections/{connection_id}/revisions"
    ]
    problem_codes = schema["components"]["schemas"]["ProblemCode"]["enum"]

    assert collection["post"]["operationId"] == "createConnection"
    assert collection["get"]["operationId"] == "listConnections"
    assert detail["patch"]["operationId"] == "renameConnection"
    assert revisions["post"]["operationId"] == "publishConnectionRevision"
    assert "CONNECTION_NOT_FOUND" in problem_codes
    assert "CONNECTION_STATE_CONFLICT" in problem_codes
