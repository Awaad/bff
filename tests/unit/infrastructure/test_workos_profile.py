from __future__ import annotations

import httpx
import pytest
from bff_control.core.settings import WorkOSSettings
from bff_control.domains.authentication.provisioning_contracts import (
    ExternalUserProfileNotFoundError,
    ExternalUserProfileUnavailableError,
)
from bff_control.infrastructure.auth.workos_profile import WorkOSUserProfileClient


def _settings() -> WorkOSSettings:
    return WorkOSSettings.model_validate(
        {
            "api_key": "sk_test",
            "api_base_url": "https://api.workos.test",
            "user_request_timeout_seconds": 1,
        }
    )


@pytest.mark.asyncio
async def test_profile_client_returns_verified_provider_profile() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk_test"
        assert request.url.path == "/user_management/users/user_test"
        return httpx.Response(
            200,
            json={
                "id": "user_test",
                "email": " User@Example.Test ",
                "email_verified": True,
                "name": " Example User ",
            },
        )

    client = WorkOSUserProfileClient(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    profile = await client.fetch_user("user_test")

    assert profile.subject == "user_test"
    assert profile.email == "User@Example.Test"
    assert profile.email_verified is True
    assert profile.display_name == "Example User"


@pytest.mark.asyncio
async def test_profile_client_encodes_subject_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == b"/user_management/users/user%2Ftest"
        return httpx.Response(
            200,
            json={
                "id": "user/test",
                "email": "user@example.test",
                "email_verified": True,
                "name": None,
            },
        )

    client = WorkOSUserProfileClient(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    profile = await client.fetch_user("user/test")
    assert profile.subject == "user/test"


@pytest.mark.asyncio
async def test_profile_client_maps_missing_user_separately() -> None:
    client = WorkOSUserProfileClient(
        _settings(),
        transport=httpx.MockTransport(lambda _: httpx.Response(404)),
    )

    with pytest.raises(ExternalUserProfileNotFoundError):
        await client.fetch_user("missing")


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
async def test_profile_client_fails_closed_on_provider_errors(status_code: int) -> None:
    client = WorkOSUserProfileClient(
        _settings(),
        transport=httpx.MockTransport(lambda _: httpx.Response(status_code)),
    )

    with pytest.raises(ExternalUserProfileUnavailableError):
        await client.fetch_user("user_test")


@pytest.mark.asyncio
async def test_profile_client_rejects_subject_mismatch() -> None:
    client = WorkOSUserProfileClient(
        _settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "id": "different",
                    "email": "user@example.test",
                    "email_verified": True,
                    "name": None,
                },
            )
        ),
    )

    with pytest.raises(ExternalUserProfileUnavailableError):
        await client.fetch_user("user_test")
