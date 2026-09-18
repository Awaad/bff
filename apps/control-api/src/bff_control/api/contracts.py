"""Runtime interfaces owned by the HTTP transport layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from opentelemetry.trace import Tracer

from bff_control.domains.authentication.contracts import PrincipalAuthenticator
from bff_control.domains.authentication.provisioning_contracts import SessionProvisioner
from bff_control.domains.workspaces.contracts import WorkspaceManager


class DatabaseLifecycle(Protocol):
    """Database lifecycle required by the API process."""

    async def is_ready(self) -> bool: ...

    async def dispose(self) -> None: ...


class TelemetryLifecycle(Protocol):
    """Telemetry lifecycle required by the API process."""

    @property
    def tracer(self) -> Tracer: ...

    def shutdown(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ApplicationResources:
    """Process resources constructed together by the composition root."""

    database: DatabaseLifecycle
    telemetry: TelemetryLifecycle
    authenticator: PrincipalAuthenticator
    session_provisioner: SessionProvisioner | None = None
    workspace_service: WorkspaceManager | None = None
