from __future__ import annotations

from typing import Literal
from uuid import UUID

from bff_control.api.app import create_app
from bff_control.api.contracts import ApplicationResources
from bff_control.api.problems.openapi import ControlApi
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from fastapi import HTTPException
from fastapi.testclient import TestClient
from opentelemetry import trace
from pydantic import BaseModel


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


class ValidationBody(BaseModel):
    name: str
    mode: Literal["safe"]


def _app() -> ControlApi:
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=UnusedAuthenticator(),
        )
    )

    @app.post("/v1/_test/validate")
    async def validate(body: ValidationBody) -> dict[str, str]:
        return {"name": body.name}

    @app.get("/v1/_test/http")
    async def reject() -> None:
        raise HTTPException(
            status_code=429,
            detail="upstream raw detail must not escape",
            headers={"Retry-After": "5"},
        )

    @app.get("/v1/_test/internal")
    async def fail() -> None:
        raise RuntimeError("database password is secret")

    return app


def test_problem_instance_and_request_header_use_same_uuid() -> None:
    with TestClient(_app()) as client:
        response = client.get("/missing")
    assert response.status_code == 404
    request_id = response.headers["x-request-id"]
    assert UUID(request_id).version == 7
    assert response.json()["request_id"] == request_id
    assert response.json()["instance"] == f"urn:uuid:{request_id}"
    assert response.json()["code"] == "REQUEST_NOT_FOUND"


def test_validation_error_is_safe_and_machine_readable() -> None:
    with TestClient(_app()) as client:
        response = client.post(
            "/v1/_test/validate",
            json={"mode": "dangerous"},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"
    assert response.json()["errors"] == [
        {
            "pointer": "#/body/name",
            "code": "REQUIRED",
            "detail": "Field is required.",
        },
        {
            "pointer": "#/body/mode",
            "code": "INVALID_VALUE",
            "detail": "Value is invalid.",
        },
    ]
    assert "dangerous" not in response.text


def test_generic_http_exception_does_not_expose_raw_detail() -> None:
    with TestClient(_app()) as client:
        response = client.get("/v1/_test/http")
    assert response.status_code == 429
    assert response.json()["code"] == "REQUEST_REJECTED"
    assert response.headers["retry-after"] == "5"
    assert "upstream raw detail" not in response.text


def test_unhandled_exception_is_generic_and_correlated() -> None:
    with TestClient(_app(), raise_server_exceptions=False) as client:
        response = client.get("/v1/_test/internal")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "database password" not in response.text
