"""Runtime interfaces owned by the HTTP transport layer."""

from __future__ import annotations

from typing import Protocol

from opentelemetry.trace import Tracer


class DatabaseLifecycle(Protocol):
    """Database lifecycle required by the API process."""

    async def is_ready(self) -> bool: ...

    async def dispose(self) -> None: ...


class TelemetryLifecycle(Protocol):
    """Telemetry lifecycle required by the API process."""

    @property
    def tracer(self) -> Tracer: ...

    def shutdown(self) -> None: ...
