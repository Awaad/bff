"""SQLAlchemy repository for Workspace bootstrap and membership authorization."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from bff_control.core.ids import uuid7
from bff_control.domains.workspaces.models import (
    WorkspaceAccess,
    WorkspaceRole,
    WorkspaceStatus,
)
from bff_control.infrastructure.db.database import Database

_INSERT_WORKSPACE = text(
    """
    INSERT INTO app.workspaces (
        id,
        name
    ) VALUES (
        :workspace_id,
        :name
    )
    RETURNING id, name, status, created_at, updated_at
    """
)

_INSERT_OWNER_MEMBERSHIP = text(
    """
    INSERT INTO app.workspace_memberships (
        id,
        workspace_id,
        user_id,
        role
    ) VALUES (
        :membership_id,
        :workspace_id,
        :user_id,
        'OWNER'
    )
    """
)

_INSERT_WORKSPACE_AUDIT = text(
    """
    INSERT INTO app.audit_events (
        id,
        workspace_id,
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
        'TENANT',
        'USER',
        :user_id,
        'OWNER',
        :user_id,
        'WORKSPACE_CREATED',
        'SUCCEEDED',
        'WORKSPACE',
        :workspace_id,
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
    SELECT
        workspaces.id AS workspace_id,
        workspaces.name AS name,
        workspaces.status AS status,
        memberships.role AS role,
        workspaces.created_at AS created_at,
        workspaces.updated_at AS updated_at
    FROM app.workspace_memberships AS memberships
    JOIN app.workspaces AS workspaces
      ON workspaces.id = memberships.workspace_id
    WHERE memberships.user_id = :user_id
      AND memberships.ended_at IS NULL
    ORDER BY workspaces.created_at ASC, workspaces.id ASC
    """
)

_GET_FOR_USER = text(
    """
    SELECT
        workspaces.id AS workspace_id,
        workspaces.name AS name,
        workspaces.status AS status,
        memberships.role AS role,
        workspaces.created_at AS created_at,
        workspaces.updated_at AS updated_at
    FROM app.workspace_memberships AS memberships
    JOIN app.workspaces AS workspaces
      ON workspaces.id = memberships.workspace_id
    WHERE memberships.user_id = :user_id
      AND memberships.workspace_id = :workspace_id
      AND memberships.ended_at IS NULL
    """
)


class SqlAlchemyWorkspaceRepository:
    """Persist Workspace operations using the control-plane database."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_owned_workspace(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
    ) -> WorkspaceAccess:
        workspace_id = uuid7()
        membership_id = uuid7()

        async with self._database.session() as session, session.begin():
            inserted = await session.execute(
                _INSERT_WORKSPACE,
                {
                    "workspace_id": workspace_id,
                    "name": name,
                },
            )
            row = inserted.mappings().one()

            await session.execute(
                _INSERT_OWNER_MEMBERSHIP,
                {
                    "membership_id": membership_id,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                },
            )
            await session.execute(
                _INSERT_WORKSPACE_AUDIT,
                {
                    "audit_id": uuid7(),
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "name": name,
                    "after_json": json.dumps(
                        {
                            "name": name,
                            "status": WorkspaceStatus.ACTIVE.value,
                            "role": WorkspaceRole.OWNER.value,
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    "request_id": str(request_id),
                    "trace_id": trace_id,
                    "session_id": str(auth_session_id),
                },
            )

        return WorkspaceAccess(
            workspace_id=self._uuid_value(row["id"], "workspace_id"),
            name=self._string_value(row["name"], "name"),
            status=self._workspace_status(row["status"]),
            role=WorkspaceRole.OWNER,
            created_at=self._datetime_value(row["created_at"], "created_at"),
            updated_at=self._datetime_value(row["updated_at"], "updated_at"),
        )

    async def list_for_user(self, user_id: UUID) -> tuple[WorkspaceAccess, ...]:
        async with self._database.session() as session:
            result = await session.execute(_LIST_FOR_USER, {"user_id": user_id})
            rows = result.mappings().all()
        return tuple(self._access_from_row(row) for row in rows)

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
    ) -> WorkspaceAccess | None:
        async with self._database.session() as session:
            result = await session.execute(
                _GET_FOR_USER,
                {
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                },
            )
            row = result.mappings().one_or_none()
        if row is None:
            return None
        return self._access_from_row(row)

    @classmethod
    def _access_from_row(cls, row: RowMapping) -> WorkspaceAccess:
        return WorkspaceAccess(
            workspace_id=cls._uuid_value(row["workspace_id"], "workspace_id"),
            name=cls._string_value(row["name"], "name"),
            status=cls._workspace_status(row["status"]),
            role=cls._workspace_role(row["role"]),
            created_at=cls._datetime_value(row["created_at"], "created_at"),
            updated_at=cls._datetime_value(row["updated_at"], "updated_at"),
        )

    @staticmethod
    def _uuid_value(value: object, field: str) -> UUID:
        if not isinstance(value, UUID):
            raise TypeError(f"workspace query returned invalid {field}")
        return value

    @staticmethod
    def _string_value(value: object, field: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"workspace query returned invalid {field}")
        return value

    @staticmethod
    def _datetime_value(value: object, field: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"workspace query returned invalid {field}")
        return value

    @classmethod
    def _workspace_status(cls, value: object) -> WorkspaceStatus:
        return WorkspaceStatus(cls._string_value(value, "status"))

    @classmethod
    def _workspace_role(cls, value: object) -> WorkspaceRole:
        return WorkspaceRole(cls._string_value(value, "role"))
