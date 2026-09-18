from __future__ import annotations

import pytest
from pydantic import ValidationError

from bff_control.core.settings import AuthenticationSettings, WorkOSSettings


def _auth_settings(**overrides: object) -> AuthenticationSettings:
    values: dict[str, object] = {
        "issuer": "https://example.authkit.app",
        "client_id": "client_test",
        "jwks_url": "https://example.authkit.app/oauth2/jwks",
    }
    values.update(overrides)
    return AuthenticationSettings.model_validate(values)


def _workos_settings(**overrides: object) -> WorkOSSettings:
    values: dict[str, object] = {"api_key": "sk_test"}
    values.update(overrides)
    return WorkOSSettings.model_validate(values)


def test_local_session_ttl_default_is_seven_days() -> None:
    assert _auth_settings().session_absolute_ttl_seconds == 604_800


def test_workos_settings_defaults_are_server_side_and_bounded() -> None:
    settings = _workos_settings()

    assert str(settings.api_base_url).rstrip("/") == "https://api.workos.com"
    assert settings.user_request_timeout_seconds == 5.0
    assert settings.api_key.get_secret_value() == "sk_test"


def test_workos_settings_reject_http_api_base_url() -> None:
    with pytest.raises(ValidationError):
        _workos_settings(api_base_url="http://api.workos.test")
