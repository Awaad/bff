"""Workspace authorization and input policies."""

from __future__ import annotations

from typing import Final

from bff_control.domains.workspaces.models import WorkspaceRole

MAX_WORKSPACE_NAME_LENGTH: Final = 120
_READ_ROLES: Final = frozenset(WorkspaceRole)


def normalize_workspace_name(value: str) -> str:
    """Return the canonical user-facing Workspace name or reject it."""

    normalized = value.strip()
    if not normalized:
        raise ValueError("workspace name must not be empty")
    if len(normalized) > MAX_WORKSPACE_NAME_LENGTH:
        raise ValueError(
            f"workspace name must be at most {MAX_WORKSPACE_NAME_LENGTH} characters",
        )
    return normalized


def can_read_workspace(role: WorkspaceRole) -> bool:
    """Return whether one active role may read Workspace metadata."""

    return role in _READ_ROLES
