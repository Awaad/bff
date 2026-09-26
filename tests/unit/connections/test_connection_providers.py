from __future__ import annotations

import hashlib

import pytest
from bff_control.domains.connections.providers import (
    ConnectionProviderRegistry,
    ProviderConfigurationError,
)


def test_generic_http_configuration_is_canonical_and_hash_stable() -> None:
    registry = ConnectionProviderRegistry.default()

    first = registry.publish(
        "generic_http",
        {"base_url": "  HTTPS://API.Example.COM/v1/  "},
    )
    second = registry.publish(
        "generic_http",
        {"base_url": "https://api.example.com:443/v1"},
    )

    assert first.configuration == {"base_url": "https://api.example.com/v1"}
    assert first.definition_schema_version == 1
    assert first.config_hash == second.config_hash
    assert (
        first.config_hash
        == hashlib.sha256(
            b'{"base_url":"https://api.example.com/v1"}',
        ).digest()
    )


@pytest.mark.parametrize(
    "configuration",
    [
        {},
        {"base_url": "http://api.example.com"},
        {"base_url": "https://user:secret@api.example.com"},
        {"base_url": "https://api.example.com?token=secret"},
        {"base_url": "https://api.example.com#fragment"},
        {"base_url": "https://api example.com"},
        {"base_url": "https://api.example.com", "extra": True},
    ],
)
def test_generic_http_configuration_rejects_unsafe_or_unknown_shape(
    configuration: dict[str, object],
) -> None:
    registry = ConnectionProviderRegistry.default()

    with pytest.raises(ProviderConfigurationError):
        registry.publish("generic_http", configuration)


def test_provider_registry_rejects_unknown_provider() -> None:
    with pytest.raises(ProviderConfigurationError, match="not supported"):
        ConnectionProviderRegistry.default().require("unknown")
