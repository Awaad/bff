from __future__ import annotations

import logging
from uuid import UUID

import pytest
from bff_control.api.app import create_app
from bff_control.api.context import current_request_context, require_request_context
from bff_control.api.contracts import ApplicationResources
from bff_control.api.problems.openapi import ControlApi
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from fastapi import Request
from fastapi.testclient import TestClient
from opentelemetry import trace


class FakeDatabase:
    async def is_ready(self) -> bool:
        return True

    async def dispose(self) -> None:
        pass


class FakeTelemetry:
    def __init__(self) -> None:
        self.tracer = trace.NoOpTracerProvider().get_tracer("test")

    def shutdown(self) -> None:
        pass


class UnusedAuthenticator:
    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        raise AssertionError("authenticator should not be used")


def _app() -> ControlApi:
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=UnusedAuthenticator(),
        )
    )

    @app.get("/v1/_test/context")
    async def context_endpoint(request: Request) -> dict[str, str | None]:
        context = require_request_context(request)
        assert current_request_context() == context
        return {
            "request_id": str(context.request_id),
            "trace_id": context.trace_id,
        }

    return app


def test_server_owns_canonical_request_id() -> None:
    with TestClient(_app()) as client:
        response = client.get(
            "/v1/_test/context",
            headers={"X-Request-ID": "client-controlled-id"},
        )
    server_request_id = response.headers["x-request-id"]
    assert UUID(server_request_id).version == 7
    assert server_request_id != "client-controlled-id"
    assert response.json()["request_id"] == server_request_id
    assert current_request_context() is None


def test_unmatched_access_log_does_not_include_raw_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="bff_control.api.access")
    with TestClient(_app()) as client:
        response = client.get(
            "/secret/token-value",
            params={"api_key": "should-not-be-logged"},
        )
    assert response.status_code == 404
    records = [
        record
        for record in caplog.records
        if record.name == "bff_control.api.access"
        and record.getMessage() == "http_request_completed"
    ]
    assert records
    record = records[-1]
    extras = record.__dict__
    assert extras["route"] == "<unmatched>"
    assert extras["method"] == "GET"
    assert extras["status_code"] == 404
    assert "secret/token-value" not in record.getMessage()
    assert "should-not-be-logged" not in record.getMessage()
