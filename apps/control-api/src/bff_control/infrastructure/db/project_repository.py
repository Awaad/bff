"""SQLAlchemy repository for Project authorization and creation."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from bff_control.core.ids import uuid7
from bff_control.domains.projects.contracts import (
    ProjectCreationAuthorizer,
    ProjectWorkspaceNotFoundError,
)
from bff_control.domains.projects.models import (
    Project,
    ProjectAuthorizationRole,
    ProjectLookup,
    ProjectPage,
    ProjectPageCursor,
    ProjectPageLookup,
    ProjectStatus,
    ProjectWorkspaceContext,
    ProjectWorkspaceStatus,
)
from bff_control.infrastructure.db.database import Database

_LOCK_PROJECT_CREATION_CONTEXT = text(
    """
    SELECT
        workspaces.id AS workspace_id,
        workspaces.status AS workspace_status,
        memberships.role AS membership_role
    FROM app.workspace_memberships AS memberships
    JOIN app.workspaces AS workspaces
      ON workspaces.id = memberships.workspace_id
    WHERE memberships.user_id = :user_id
      AND memberships.workspace_id = :workspace_id
      AND memberships.ended_at IS NULL
    FOR UPDATE OF workspaces, memberships
    """
)

_INSERT_PROJECT = text(
    """
    INSERT INTO app.projects (
        id,
        workspace_id,
        name
    ) VALUES (
        :project_id,
        :workspace_id,
        :name
    )
    RETURNING
        id,
        workspace_id,
        name,
        status,
        created_at,
        updated_at,
        archived_at
    """
)

_INSERT_PROJECT_AUDIT = text(
    """
    INSERT INTO app.audit_events (
        id,
        workspace_id,
        project_id,
        scope,
        actor_type,
        actor_user_id,
        actor_role_snapshot,
        effective_user_id,
        action,
        outcome,
        resource_type,
        resource_id,
        resource_display_snapshot,
        after_json,
        request_id,
        trace_id,
        session_id,
        surface
    ) VALUES (
        :audit_id,
        :workspace_id,
        :project_id,
        'TENANT',
        'USER',
        :user_id,
        :membership_role,
        :user_id,
        'PROJECT_CREATED',
        'SUCCEEDED',
        'PROJECT',
        :project_id,
        :name,
        CAST(:after_json AS jsonb),
        :request_id,
        :trace_id,
        :session_id,
        'PUBLIC_API'
    )
    """
)

_LIST_FOR_USER = text(
    """
    WITH access AS MATERIALIZED (
        SELECT
            workspaces.id AS workspace_id,
            workspaces.status AS workspace_status,
            memberships.role AS membership_role
        FROM app.workspace_memberships AS memberships
        JOIN app.workspaces AS workspaces
          ON workspaces.id = memberships.workspace_id
        WHERE memberships.user_id = :user_id
          AND memberships.workspace_id = :workspace_id
          AND memberships.ended_at IS NULL
    )
    SELECT
        access.workspace_id AS authorized_workspace_id,
        access.workspace_status,
        access.membership_role,
        project.id AS project_id,
        project.workspace_id AS project_workspace_id,
        project.name AS project_name,
        project.status AS project_status,
        project.created_at AS project_created_at,
        project.updated_at AS project_updated_at,
        project.archived_at AS project_archived_at
    FROM access
    LEFT JOIN LATERAL (
        SELECT
            projects.id,
            projects.workspace_id,
            projects.name,
            projects.status,
            projects.created_at,
            projects.updated_at,
            projects.archived_at
        FROM app.projects AS projects
        WHERE projects.workspace_id = access.workspace_id
          AND (
              CAST(:cursor_created_at AS timestamptz) IS NULL
              OR (projects.created_at, projects.id) < (
                  CAST(:cursor_created_at AS timestamptz),
                  CAST(:cursor_project_id AS uuid)
              )
          )
        ORDER BY projects.created_at DESC, projects.id DESC
        LIMIT :fetch_limit
    ) AS project ON TRUE
    ORDER BY project.created_at DESC NULLS LAST, project.id DESC NULLS LAST
    """
)

_GET_FOR_USER = text(
    """
    WITH access AS MATERIALIZED (
        SELECT
            workspaces.id AS workspace_id,
            workspaces.status AS workspace_status,
            memberships.role AS membership_role
        FROM app.workspace_memberships AS memberships
        JOIN app.workspaces AS workspaces
          ON workspaces.id = memberships.workspace_id
        WHERE memberships.user_id = :user_id
          AND memberships.workspace_id = :workspace_id
          AND memberships.ended_at IS NULL
    )
    SELECT
        access.workspace_id AS authorized_workspace_id,
        access.workspace_status,
        access.membership_role,
        projects.id AS project_id,
        projects.workspace_id AS project_workspace_id,
        projects.name AS project_name,
        projects.status AS project_status,
        projects.created_at AS project_created_at,
        projects.updated_at AS project_updated_at,
        projects.archived_at AS project_archived_at
    FROM access
    LEFT JOIN app.projects AS projects
      ON projects.workspace_id = access.workspace_id
     AND projects.id = :project_id
    """
)


class SqlAlchemyProjectRepository:
    """Persist Project operations through membership-constrained queries."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_project(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
        authorize: ProjectCreationAuthorizer,
    ) -> Project:
        project_id = uuid7()

        async with self._database.session() as session, session.begin():
            context_result = await session.execute(
                _LOCK_PROJECT_CREATION_CONTEXT,
                {
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                },
            )
            context_row = context_result.mappings().one_or_none()
            if context_row is None:
                raise ProjectWorkspaceNotFoundError("workspace not found")

            context = self._context_from_row(context_row)
            authorize(context)

            inserted = await session.execute(
                _INSERT_PROJECT,
                {
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                    "name": name,
                },
            )
            project_row = inserted.mappings().one()

            await session.execute(
                _INSERT_PROJECT_AUDIT,
                {
                    "audit_id": uuid7(),
                    "workspace_id": workspace_id,
                    "project_id": project_id,
                    "user_id": user_id,
                    "membership_role": context.role.value,
                    "name": name,
                    "after_json": json.dumps(
                        {
                            "name": name,
                            "status": ProjectStatus.ACTIVE.value,
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    "request_id": str(request_id),
                    "trace_id": trace_id,
                    "session_id": str(auth_session_id),
                },
            )

        return self._project_from_insert_row(project_row)

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ProjectPageCursor | None,
        limit: int,
    ) -> ProjectPageLookup:
        async with self._database.session() as session:
            result = await session.execute(
                _LIST_FOR_USER,
                {
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "cursor_created_at": cursor.created_at if cursor else None,
                    "cursor_project_id": cursor.project_id if cursor else None,
                    "fetch_limit": limit + 1,
                },
            )
            rows = result.mappings().all()

        if not rows:
            return ProjectPageLookup(
                context=None,
                page=ProjectPage(items=(), next_cursor=None),
            )

        context = self._context_from_row(rows[0])
        projects = [
            self._project_from_list_row(row) for row in rows if row["project_id"] is not None
        ]
        has_more = len(projects) > limit
        visible = projects[:limit]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = ProjectPageCursor(
                created_at=last.created_at,
                project_id=last.project_id,
            )

        return ProjectPageLookup(
            context=context,
            page=ProjectPage(items=tuple(visible), next_cursor=next_cursor),
        )

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        project_id: UUID,
    ) -> ProjectLookup:
        async with self._database.session() as session:
            result = await session.execute(
                _GET_FOR_USER,
                {
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "project_id": project_id,
                },
            )
            row = result.mappings().one_or_none()

        if row is None:
            return ProjectLookup(context=None, project=None)
        project = None
        if row["project_id"] is not None:
            project = self._project_from_list_row(row)
        return ProjectLookup(
            context=self._context_from_row(row),
            project=project,
        )

    @classmethod
    def _context_from_row(cls, row: RowMapping) -> ProjectWorkspaceContext:
        return ProjectWorkspaceContext(
            workspace_id=cls._uuid_value(
                row["authorized_workspace_id"]
                if "authorized_workspace_id" in row
                else row["workspace_id"],
                "workspace_id",
            ),
            status=ProjectWorkspaceStatus(
                cls._string_value(row["workspace_status"], "workspace_status"),
            ),
            role=ProjectAuthorizationRole(
                cls._string_value(row["membership_role"], "membership_role"),
            ),
        )

    @classmethod
    def _project_from_insert_row(cls, row: RowMapping) -> Project:
        return Project(
            project_id=cls._uuid_value(row["id"], "project_id"),
            workspace_id=cls._uuid_value(row["workspace_id"], "workspace_id"),
            name=cls._string_value(row["name"], "name"),
            status=ProjectStatus(cls._string_value(row["status"], "project_status")),
            created_at=cls._datetime_value(row["created_at"], "created_at"),
            updated_at=cls._datetime_value(row["updated_at"], "updated_at"),
            archived_at=cls._optional_datetime_value(row["archived_at"], "archived_at"),
        )

    @classmethod
    def _project_from_list_row(cls, row: RowMapping) -> Project:
        return Project(
            project_id=cls._uuid_value(row["project_id"], "project_id"),
            workspace_id=cls._uuid_value(
                row["project_workspace_id"],
                "project_workspace_id",
            ),
            name=cls._string_value(row["project_name"], "project_name"),
            status=ProjectStatus(
                cls._string_value(row["project_status"], "project_status"),
            ),
            created_at=cls._datetime_value(
                row["project_created_at"],
                "project_created_at",
            ),
            updated_at=cls._datetime_value(
                row["project_updated_at"],
                "project_updated_at",
            ),
            archived_at=cls._optional_datetime_value(
                row["project_archived_at"],
                "project_archived_at",
            ),
        )

    @staticmethod
    def _uuid_value(value: object, field: str) -> UUID:
        if not isinstance(value, UUID):
            raise TypeError(f"project query returned invalid {field}")
        return value

    @staticmethod
    def _string_value(value: object, field: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"project query returned invalid {field}")
        return value

    @staticmethod
    def _datetime_value(value: object, field: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"project query returned invalid {field}")
        return value

    @classmethod
    def _optional_datetime_value(
        cls,
        value: object,
        field: str,
    ) -> datetime | None:
        if value is None:
            return None
        return cls._datetime_value(value, field)
