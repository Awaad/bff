"""Typed Connection provider configuration registry."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit

from bff_control.domains.connections.models import (
    JsonObject,
    PublishedConnectionConfiguration,
)

GENERIC_HTTP_PROVIDER_KEY: Final = "generic_http"


class ProviderConfigurationError(ValueError):
    """Raised when provider configuration cannot be safely canonicalized."""


class ConnectionProvider(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def definition_schema_version(self) -> int: ...

    def canonicalize(self, configuration: Mapping[str, object]) -> JsonObject: ...


@dataclass(frozen=True, slots=True)
class GenericHttpProvider:
    key: str = GENERIC_HTTP_PROVIDER_KEY
    definition_schema_version: int = 1

    def canonicalize(self, configuration: Mapping[str, object]) -> JsonObject:
        if set(configuration) != {"base_url"}:
            raise ProviderConfigurationError(
                "generic_http configuration must contain only base_url",
            )
        base_url = configuration.get("base_url")
        if not isinstance(base_url, str):
            raise ProviderConfigurationError("base_url must be a string")
        normalized = self._normalize_base_url(base_url)
        return {"base_url": normalized}

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ProviderConfigurationError("base_url must not be empty")
        try:
            parsed = urlsplit(candidate)
            port = parsed.port
        except ValueError as exc:
            raise ProviderConfigurationError("base_url is not a valid URL") from exc
        if parsed.scheme.casefold() != "https":
            raise ProviderConfigurationError("base_url must use https")
        if parsed.hostname is None:
            raise ProviderConfigurationError("base_url must include a host")
        if parsed.username is not None or parsed.password is not None:
            raise ProviderConfigurationError("base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ProviderConfigurationError(
                "base_url must not contain a query string or fragment",
            )

        host = parsed.hostname.casefold()
        if any(character.isspace() for character in host):
            raise ProviderConfigurationError("base_url host must not contain whitespace")
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = host if port is None or port == 443 else f"{host}:{port}"
        path = parsed.path.rstrip("/")
        normalized = SplitResult(
            scheme="https",
            netloc=netloc,
            path=path,
            query="",
            fragment="",
        )
        return urlunsplit(normalized)


class ConnectionProviderRegistry:
    """Resolve and compile typed provider configuration."""

    def __init__(self, providers: tuple[ConnectionProvider, ...]) -> None:
        mapped = {provider.key: provider for provider in providers}
        if len(mapped) != len(providers):
            raise ValueError("provider keys must be unique")
        self._providers = mapped

    @classmethod
    def default(cls) -> ConnectionProviderRegistry:
        return cls((GenericHttpProvider(),))

    def require(self, provider_key: str) -> ConnectionProvider:
        try:
            return self._providers[provider_key]
        except KeyError as exc:
            raise ProviderConfigurationError("provider key is not supported") from exc

    def publish(
        self,
        provider_key: str,
        configuration: Mapping[str, object],
    ) -> PublishedConnectionConfiguration:
        provider = self.require(provider_key)
        canonical = provider.canonicalize(configuration)
        serialized = json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return PublishedConnectionConfiguration(
            definition_schema_version=provider.definition_schema_version,
            configuration=canonical,
            config_hash=hashlib.sha256(serialized).digest(),
        )

    def compile_draft(
        self,
        provider_key: str,
        configuration: Mapping[str, object],
    ) -> JsonObject:
        """Validate non-secret draft state using the provider's typed schema."""

        return self.require(provider_key).canonicalize(configuration)
