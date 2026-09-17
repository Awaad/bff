from __future__ import annotations

import pytest
from bff_control.core.settings import AuthenticationSettings
from pydantic import ValidationError


def _settings(**overrides: object) -> AuthenticationSettings:
    values: dict[str, object] = {
        "issuer": "https://example.authkit.app",
        "client_id": "client_test",
        "jwks_url": "https://example.authkit.app/oauth2/jwks",
    }
    values.update(overrides)
    return AuthenticationSettings.model_validate(values)


def test_authentication_settings_defaults_are_bounded() -> None:
    settings = _settings()

    assert settings.jwks_cache_ttl_seconds == 300.0
    assert settings.jwks_request_timeout_seconds == 5.0
    assert settings.jwks_unknown_kid_cooldown_seconds == 30.0
    assert settings.jwt_leeway_seconds == 30
    assert settings.max_bearer_token_length == 16_384


@pytest.mark.parametrize(
    "issuer",
    [
        "http://example.authkit.app",
        " https://example.authkit.app",
        "https://user@example.authkit.app",
        "https://example.authkit.app?query=1",
        "https://example.authkit.app#fragment",
    ],
)
def test_authentication_settings_reject_untrusted_issuer_shapes(issuer: str) -> None:
    with pytest.raises(ValidationError):
        _settings(issuer=issuer)


def test_authentication_settings_reject_http_jwks_url() -> None:
    with pytest.raises(ValidationError):
        _settings(jwks_url="http://example.authkit.app/oauth2/jwks")


@pytest.mark.parametrize("client_id", ["", " client_test", "client_test "])
def test_authentication_settings_reject_invalid_client_id(client_id: str) -> None:
    with pytest.raises(ValidationError):
        _settings(client_id=client_id)
