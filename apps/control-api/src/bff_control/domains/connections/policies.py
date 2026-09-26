"""Connection authorization, lifecycle, and input policies."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final
from uuid import UUID

from bff_control.domains.connections.models import (
    ConnectionAccessMode,
    ConnectionAccessPolicy,
    ConnectionAuthorizationRole,
    ConnectionLifecycleAction,
    ConnectionStatus,
    ConnectionWorkspaceStatus,
    JsonObject,
)

MAX_CONNECTION_NAME_LENGTH: Final = 120
DEFAULT_CONNECTION_PAGE_LIMIT: Final = 50
MAX_CONNECTION_PAGE_LIMIT: Final = 100
DEFAULT_CONNECTION_REVISION_PAGE_LIMIT: Final = 50
MAX_CONNECTION_REVISION_PAGE_LIMIT: Final = 100
MAX_SELECTED_PROJECTS: Final = 1000

_READ_ROLES: Final = frozenset(ConnectionAuthorizationRole)
_AUTHOR_ROLES: Final = frozenset(
    {
        ConnectionAuthorizationRole.OWNER,
        ConnectionAuthorizationRole.ADMIN,
        ConnectionAuthorizationRole.BUILDER,
    }
)
_LIFECYCLE_ROLES: Final = frozenset(
    {
        ConnectionAuthorizationRole.OWNER,
        ConnectionAuthorizationRole.ADMIN,
    }
)


def normalize_connection_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("connection name must not be empty")
    if len(normalized) > MAX_CONNECTION_NAME_LENGTH:
        raise ValueError(
            f"connection name must be at most {MAX_CONNECTION_NAME_LENGTH} characters",
        )
    return normalized


def normalize_provider_key(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("provider key must not be empty")
    if normalized != normalized.casefold():
        raise ValueError("provider key must be lowercase")
    return normalized


def normalize_access_policy(
    mode: ConnectionAccessMode,
    project_ids: Iterable[UUID],
) -> ConnectionAccessPolicy:
    provided = tuple(project_ids)
    unique = tuple(dict.fromkeys(provided))
    if len(unique) != len(provided):
        raise ValueError("selected Project IDs must be unique")
    if len(unique) > MAX_SELECTED_PROJECTS:
        raise ValueError(
            f"selected Project IDs must contain at most {MAX_SELECTED_PROJECTS} items",
        )
    if mode is ConnectionAccessMode.WORKSPACE and unique:
        raise ValueError("WORKSPACE access cannot include selected Project IDs")
    return ConnectionAccessPolicy(
        mode=mode,
        project_ids=tuple(sorted(unique, key=str)),
    )


def normalize_draft_configuration(value: Mapping[str, object]) -> JsonObject:
    return dict(value)


def validate_connection_page_limit(value: int) -> int:
    if value < 1 or value > MAX_CONNECTION_PAGE_LIMIT:
        raise ValueError(
            f"connection page limit must be between 1 and {MAX_CONNECTION_PAGE_LIMIT}",
        )
    return value


def validate_connection_revision_page_limit(value: int) -> int:
    if value < 1 or value > MAX_CONNECTION_REVISION_PAGE_LIMIT:
        raise ValueError(
            "connection revision page limit must be between 1 and "
            f"{MAX_CONNECTION_REVISION_PAGE_LIMIT}",
        )
    return value


def validate_before_revision(value: int | None) -> int | None:
    if value is not None and value < 1:
        raise ValueError("before_revision must be a positive revision number")
    return value


def can_read_connections(role: ConnectionAuthorizationRole) -> bool:
    return role in _READ_ROLES


def can_author_connections(role: ConnectionAuthorizationRole) -> bool:
    return role in _AUTHOR_ROLES


def can_manage_connection_lifecycle(role: ConnectionAuthorizationRole) -> bool:
    return role in _LIFECYCLE_ROLES


def can_create_with_access(
    role: ConnectionAuthorizationRole,
    mode: ConnectionAccessMode,
) -> bool:
    if role not in _AUTHOR_ROLES:
        return False
    return (
        role is not ConnectionAuthorizationRole.BUILDER
        or mode is ConnectionAccessMode.SELECTED_PROJECTS
    )


def can_replace_access(
    role: ConnectionAuthorizationRole,
    current_mode: ConnectionAccessMode,
    requested_mode: ConnectionAccessMode,
) -> bool:
    if role in _LIFECYCLE_ROLES:
        return True
    return (
        role is ConnectionAuthorizationRole.BUILDER
        and current_mode is ConnectionAccessMode.SELECTED_PROJECTS
        and requested_mode is ConnectionAccessMode.SELECTED_PROJECTS
    )


def workspace_allows_connection_mutation(status: ConnectionWorkspaceStatus) -> bool:
    return status is ConnectionWorkspaceStatus.ACTIVE


def workspace_allows_lifecycle_action(
    status: ConnectionWorkspaceStatus,
    action: ConnectionLifecycleAction,
) -> bool:
    if action is ConnectionLifecycleAction.DISABLE:
        return status in {
            ConnectionWorkspaceStatus.ACTIVE,
            ConnectionWorkspaceStatus.SUSPENDED,
        }
    return status is ConnectionWorkspaceStatus.ACTIVE


def connection_allows_authoring(status: ConnectionStatus) -> bool:
    return status is not ConnectionStatus.ARCHIVED


def connection_allows_access_replacement(status: ConnectionStatus) -> bool:
    return status is not ConnectionStatus.ARCHIVED


def lifecycle_transition_allowed(
    current: ConnectionStatus,
    action: ConnectionLifecycleAction,
) -> bool:
    if action is ConnectionLifecycleAction.DISABLE:
        return current is ConnectionStatus.ACTIVE
    if action is ConnectionLifecycleAction.ENABLE:
        return current is ConnectionStatus.DISABLED
    return current in {
        ConnectionStatus.DRAFT,
        ConnectionStatus.ACTIVE,
        ConnectionStatus.DISABLED,
    }
