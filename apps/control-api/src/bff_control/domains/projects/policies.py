"""Project authorization and input policies."""

from __future__ import annotations

from typing import Final

from bff_control.domains.projects.models import (
    ProjectAuthorizationRole,
    ProjectWorkspaceStatus,
)

MAX_PROJECT_NAME_LENGTH: Final = 120
DEFAULT_PROJECT_PAGE_LIMIT: Final = 50
MAX_PROJECT_PAGE_LIMIT: Final = 100

_READ_ROLES: Final = frozenset(ProjectAuthorizationRole)
_CREATE_ROLES: Final = frozenset(
    {
        ProjectAuthorizationRole.OWNER,
        ProjectAuthorizationRole.ADMIN,
        ProjectAuthorizationRole.BUILDER,
    }
)


def normalize_project_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("project name must not be empty")
    if len(normalized) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError(
            f"project name must be at most {MAX_PROJECT_NAME_LENGTH} characters",
        )
    return normalized


def validate_project_page_limit(value: int) -> int:
    if value < 1 or value > MAX_PROJECT_PAGE_LIMIT:
        raise ValueError(
            f"project page limit must be between 1 and {MAX_PROJECT_PAGE_LIMIT}",
        )
    return value


def can_read_projects(role: ProjectAuthorizationRole) -> bool:
    return role in _READ_ROLES


def can_create_project(role: ProjectAuthorizationRole) -> bool:
    return role in _CREATE_ROLES


def workspace_allows_project_creation(status: ProjectWorkspaceStatus) -> bool:
    return status is ProjectWorkspaceStatus.ACTIVE
