from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from opentelemetry import trace

from bff_control.api.app import create_app
from bff_control.api.contracts import ApplicationResources
from bff_control.domains.authentication.models import AuthenticatedPrincipal
from bff_control.domains.authentication.provisioning_contracts import (
    AccountLinkRequiredError,
    EmailVerificationRequiredError,
    ExternalUserProfileUnavailableError,
    SessionProvisioningAuthenticationError,
)
from bff_control.domains.authentication.provisioning_models import ProvisionedSession


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


class FakeProvisioner:
    def __init__(self, result: ProvisionedSession | Exception) -> None:
        self.result = result
        self.tokens: list[str] = []

    async def provision(self, token: str) -> ProvisionedSession:
        self.tokens.append(token)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _provisioned() -> ProvisionedSession:
    return ProvisionedSession(
        principal=AuthenticatedPrincipal(
            user_id=UUID("00000000-0000-7000-8000-000000000901"),
            auth_session_id=UUID("00000000-0000-7000-8000-000000000902"),
            email="user@example.test",
            display_name="User",
        ),
        expires_at=datetime.now(tz=UTC) + timedelta(days=7),
        created=True,
    )


def _client(result: ProvisionedSession | Exception) -> tuple[TestClient, FakeProvisioner]:
    provisioner = FakeProvisioner(result)
    app = create_app(
        resource_factory=lambda: ApplicationResources(
            database=FakeDatabase(),
            telemetry=FakeTelemetry(),
            authenticator=UnusedAuthenticator(),
            session_provisioner=provisioner,
        )
    )
    return TestClient(app), provisioner


def test_session_provisioning_requires_bearer_token() -> None:
    client, provisioner = _client(_provisioned())
    with client:
        response = client.post("/v1/auth/session")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert provisioner.tokens == []


def test_session_provisioning_returns_public_user_and_local_deadline() -> None:
    client, provisioner = _client(_provisioned())
    with client:
        response = client.post(
            "/v1/auth/session",
            headers={"Authorization": "Bearer provider-token"},
        )

    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": "00000000-0000-7000-8000-000000000901",
        "email": "user@example.test",
        "display_name": "User",
    }
    assert response.headers["cache-control"] == "no-store"
    assert provisioner.tokens == ["provider-token"]


def test_session_provisioning_maps_security_outcomes() -> None:
    cases = [
        (
            SessionProvisioningAuthenticationError("failed"),
            401,
            "invalid authentication credentials",
        ),
        (
            EmailVerificationRequiredError("verify"),
            403,
            "email verification required",
        ),
        (
            AccountLinkRequiredError("link"),
            409,
            "account linking required",
        ),
        (
            ExternalUserProfileUnavailableError("down"),
            503,
            "authentication service unavailable",
        ),
    ]

    for error, expected_status, expected_detail in cases:
        client, _ = _client(error)
        with client:
            response = client.post(
                "/v1/auth/session",
                headers={"Authorization": "Bearer provider-token"},
            )

        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}
