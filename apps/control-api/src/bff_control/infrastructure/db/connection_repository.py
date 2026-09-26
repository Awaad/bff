"""SQLAlchemy repository for the Connection control plane."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from bff_control.core.ids import uuid7
from bff_control.domains.connections.contracts import (
    ConnectionCreationAuthorizer,
    ConnectionDraftCompiler,
    ConnectionMutationAuthorizer,
    ConnectionNotFoundError,
    ConnectionProjectNotFoundError,
    ConnectionPublicationCompiler,
    ConnectionStateConflictError,
    ConnectionWorkspaceNotFoundError,
)
from bff_control.domains.connections.models import (
    Connection,
    ConnectionAccessMode,
    ConnectionAccessPolicy,
    ConnectionAuthorizationRole,
    ConnectionDraft,
    ConnectionDraftLookup,
    ConnectionLifecycleAction,
    ConnectionLookup,
    ConnectionMutationContext,
    ConnectionPage,
    ConnectionPageCursor,
    ConnectionPageLookup,
    ConnectionRevision,
    ConnectionRevisionLookup,
    ConnectionRevisionMetadata,
    ConnectionRevisionPage,
    ConnectionRevisionPageLookup,
    ConnectionStatus,
    ConnectionWorkspaceContext,
    ConnectionWorkspaceStatus,
    JsonObject,
)
from bff_control.infrastructure.db.database import Database

_LOCK_WORKSPACE_CONTEXT = text(
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

_READ_WORKSPACE_CONTEXT = text(
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
    """
)

_LOCK_CONNECTION = text(
    """
    SELECT id, provider_key, access_mode, status
    FROM app.connections
    WHERE workspace_id = :workspace_id
      AND id = :connection_id
    FOR UPDATE
    """
)

_READ_CONNECTION_CONTEXT = text(
    """
    SELECT id, provider_key, access_mode, status
    FROM app.connections
    WHERE workspace_id = :workspace_id
      AND id = :connection_id
    """
)

_INSERT_CONNECTION = text(
    """
    INSERT INTO app.connections (
        id,
        workspace_id,
        name,
        provider_key,
        access_mode,
        status
    ) VALUES (
        :connection_id,
        :workspace_id,
        :name,
        :provider_key,
        :access_mode,
        'DRAFT'
    )
    """
)

_INSERT_PROJECT_ACCESS = text(
    """
    INSERT INTO app.connection_project_access (
        workspace_id,
        connection_id,
        project_id,
        granted_by_user_id
    ) VALUES (
        :workspace_id,
        :connection_id,
        :project_id,
        :user_id
    )
    """
)

_LOCK_SELECTED_PROJECTS = text(
    """
    SELECT id
    FROM app.projects
    WHERE workspace_id = :workspace_id
      AND id = ANY(CAST(:project_ids AS uuid[]))
    FOR UPDATE
    """
)

_SELECT_CONNECTION = text(
    """
    SELECT
        connections.id AS connection_id,
        connections.workspace_id AS connection_workspace_id,
        connections.name AS connection_name,
        connections.provider_key AS connection_provider_key,
        connections.access_mode AS connection_access_mode,
        connections.status AS connection_status,
        connections.created_at AS connection_created_at,
        connections.updated_at AS connection_updated_at,
        connections.archived_at AS connection_archived_at,
        ARRAY(
            SELECT access.project_id
            FROM app.connection_project_access AS access
            WHERE access.connection_id = connections.id
            ORDER BY access.project_id
        ) AS connection_project_ids
    FROM app.connections AS connections
    WHERE connections.workspace_id = :workspace_id
      AND connections.id = :connection_id
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
        connection.connection_id,
        connection.connection_workspace_id,
        connection.connection_name,
        connection.connection_provider_key,
        connection.connection_access_mode,
        connection.connection_status,
        connection.connection_created_at,
        connection.connection_updated_at,
        connection.connection_archived_at,
        connection.connection_project_ids
    FROM access
    LEFT JOIN LATERAL (
        SELECT
            connections.id AS connection_id,
            connections.workspace_id AS connection_workspace_id,
            connections.name AS connection_name,
            connections.provider_key AS connection_provider_key,
            connections.access_mode AS connection_access_mode,
            connections.status AS connection_status,
            connections.created_at AS connection_created_at,
            connections.updated_at AS connection_updated_at,
            connections.archived_at AS connection_archived_at,
            ARRAY(
                SELECT project_access.project_id
                FROM app.connection_project_access AS project_access
                WHERE project_access.connection_id = connections.id
                ORDER BY project_access.project_id
            ) AS connection_project_ids
        FROM app.connections AS connections
        WHERE connections.workspace_id = access.workspace_id
          AND (
              CAST(:cursor_created_at AS timestamptz) IS NULL
              OR (connections.created_at, connections.id) < (
                  CAST(:cursor_created_at AS timestamptz),
                  CAST(:cursor_connection_id AS uuid)
              )
          )
        ORDER BY connections.created_at DESC, connections.id DESC
        LIMIT :fetch_limit
    ) AS connection ON TRUE
    ORDER BY
        connection.connection_created_at DESC NULLS LAST,
        connection.connection_id DESC NULLS LAST
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
        connections.id AS connection_id,
        connections.workspace_id AS connection_workspace_id,
        connections.name AS connection_name,
        connections.provider_key AS connection_provider_key,
        connections.access_mode AS connection_access_mode,
        connections.status AS connection_status,
        connections.created_at AS connection_created_at,
        connections.updated_at AS connection_updated_at,
        connections.archived_at AS connection_archived_at,
        CASE WHEN connections.id IS NULL THEN ARRAY[]::uuid[] ELSE ARRAY(
            SELECT project_access.project_id
            FROM app.connection_project_access AS project_access
            WHERE project_access.connection_id = connections.id
            ORDER BY project_access.project_id
        ) END AS connection_project_ids
    FROM access
    LEFT JOIN app.connections AS connections
      ON connections.workspace_id = access.workspace_id
     AND connections.id = :connection_id
    """
)

_RENAME_CONNECTION = text(
    """
    UPDATE app.connections
    SET name = :name, updated_at = now()
    WHERE workspace_id = :workspace_id
      AND id = :connection_id
    """
)

_SELECT_DRAFT = text(
    """
    SELECT
        connection_id,
        workspace_id,
        draft_json,
        updated_by_user_id,
        updated_at
    FROM app.connection_drafts
    WHERE workspace_id = :workspace_id
      AND connection_id = :connection_id
    """
)

_LOCK_DRAFT = text(
    """
    SELECT draft_json
    FROM app.connection_drafts
    WHERE workspace_id = :workspace_id
      AND connection_id = :connection_id
    FOR UPDATE
    """
)

_UPSERT_DRAFT = text(
    """
    INSERT INTO app.connection_drafts (
        connection_id,
        workspace_id,
        draft_json,
        updated_by_user_id
    ) VALUES (
        :connection_id,
        :workspace_id,
        CAST(:draft_json AS jsonb),
        :user_id
    )
    ON CONFLICT (connection_id) DO UPDATE
    SET
        draft_json = EXCLUDED.draft_json,
        updated_by_user_id = EXCLUDED.updated_by_user_id,
        updated_at = now()
    RETURNING connection_id, workspace_id, draft_json, updated_by_user_id, updated_at
    """
)

_LIST_REVISIONS = text(
    """
    SELECT
        id,
        workspace_id,
        connection_id,
        revision_number,
        definition_schema_version,
        encode(config_hash, 'hex') AS config_hash_hex,
        created_by_user_id,
        created_at
    FROM app.connection_revisions
    WHERE workspace_id = :workspace_id
      AND connection_id = :connection_id
      AND (
          CAST(:before_revision AS bigint) IS NULL
          OR revision_number < CAST(:before_revision AS bigint)
      )
    ORDER BY revision_number DESC
    LIMIT :fetch_limit
    """
)

_GET_REVISION = text(
    """
    SELECT
        id,
        workspace_id,
        connection_id,
        revision_number,
        definition_schema_version,
        config_json,
        encode(config_hash, 'hex') AS config_hash_hex,
        created_by_user_id,
        created_at
    FROM app.connection_revisions
    WHERE workspace_id = :workspace_id
      AND connection_id = :connection_id
      AND id = :revision_id
    """
)

_NEXT_REVISION_NUMBER = text(
    """
    SELECT COALESCE(MAX(revision_number), 0) + 1
    FROM app.connection_revisions
    WHERE connection_id = :connection_id
    """
)

_INSERT_REVISION = text(
    """
    INSERT INTO app.connection_revisions (
        id,
        workspace_id,
        connection_id,
        revision_number,
        definition_schema_version,
        config_json,
        config_hash,
        created_by_user_id
    ) VALUES (
        :revision_id,
        :workspace_id,
        :connection_id,
        :revision_number,
        :definition_schema_version,
        CAST(:config_json AS jsonb),
        :config_hash,
        :user_id
    )
    RETURNING
        id,
        workspace_id,
        connection_id,
        revision_number,
        definition_schema_version,
        config_json,
        encode(config_hash, 'hex') AS config_hash_hex,
        created_by_user_id,
        created_at
    """
)

_ACTIVATE_DRAFT_CONNECTION = text(
    """
    UPDATE app.connections
    SET status = 'ACTIVE', updated_at = now()
    WHERE workspace_id = :workspace_id
      AND id = :connection_id
      AND status = 'DRAFT'
    """
)

_DELETE_PROJECT_ACCESS = text(
    """
    DELETE FROM app.connection_project_access
    WHERE connection_id = :connection_id
    """
)

_UPDATE_ACCESS_MODE = text(
    """
    UPDATE app.connections
    SET access_mode = :access_mode, updated_at = now()
    WHERE workspace_id = :workspace_id
      AND id = :connection_id
    """
)

_UPDATE_LIFECYCLE = text(
    """
    UPDATE app.connections
    SET
        status = :status,
        archived_at = CASE WHEN :status = 'ARCHIVED' THEN now() ELSE archived_at END,
        updated_at = now()
    WHERE workspace_id = :workspace_id
      AND id = :connection_id
    """
)

_INSERT_AUDIT = text(
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
        before_json,
        after_json,
        change_json,
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
        :membership_role,
        :user_id,
        :action,
        'SUCCEEDED',
        'CONNECTION',
        :connection_id,
        :name,
        CAST(:before_json AS jsonb),
        CAST(:after_json AS jsonb),
        CAST(:change_json AS jsonb),
        :request_id,
        :trace_id,
        :session_id,
        'PUBLIC_API'
    )
    """
)


class SqlAlchemyConnectionRepository:
    """Persist Connection operations through membership-constrained queries."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_connection(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        name: str,
        provider_key: str,
        access_policy: ConnectionAccessPolicy,
        request_id: UUID,
        trace_id: str | None,
        authorize: ConnectionCreationAuthorizer,
    ) -> Connection:
        connection_id = uuid7()
        async with self._database.session() as session, session.begin():
            context = await self._workspace_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                lock=True,
            )
            authorize(context)
            await self._validate_projects(
                session,
                workspace_id=workspace_id,
                project_ids=access_policy.project_ids,
            )
            await session.execute(
                _INSERT_CONNECTION,
                {
                    "connection_id": connection_id,
                    "workspace_id": workspace_id,
                    "name": name,
                    "provider_key": provider_key,
                    "access_mode": access_policy.mode.value,
                },
            )
            await self._insert_project_access(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
                user_id=user_id,
                project_ids=access_policy.project_ids,
            )
            await self._audit(
                session,
                context=context,
                user_id=user_id,
                auth_session_id=auth_session_id,
                connection_id=connection_id,
                name=name,
                action="CONNECTION_CREATED",
                request_id=request_id,
                trace_id=trace_id,
                after={
                    "access_mode": access_policy.mode.value,
                    "name": name,
                    "project_ids": [str(item) for item in access_policy.project_ids],
                    "provider_key": provider_key,
                    "status": ConnectionStatus.DRAFT.value,
                },
            )
            connection = await self._fetch_connection(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
            )
        return connection

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ConnectionPageCursor | None,
        limit: int,
    ) -> ConnectionPageLookup:
        async with self._database.session() as session:
            result = await session.execute(
                _LIST_FOR_USER,
                {
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "cursor_created_at": cursor.created_at if cursor else None,
                    "cursor_connection_id": cursor.connection_id if cursor else None,
                    "fetch_limit": limit + 1,
                },
            )
            rows = result.mappings().all()
        if not rows:
            return ConnectionPageLookup(
                context=None,
                page=ConnectionPage(items=(), next_cursor=None),
            )
        context = self._workspace_context_from_row(rows[0])
        connections = [
            self._connection_from_row(row) for row in rows if row["connection_id"] is not None
        ]
        has_more = len(connections) > limit
        visible = connections[:limit]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = ConnectionPageCursor(
                created_at=last.created_at,
                connection_id=last.connection_id,
            )
        return ConnectionPageLookup(
            context=context,
            page=ConnectionPage(items=tuple(visible), next_cursor=next_cursor),
        )

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> ConnectionLookup:
        async with self._database.session() as session:
            result = await session.execute(
                _GET_FOR_USER,
                {
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                },
            )
            row = result.mappings().one_or_none()
        if row is None:
            return ConnectionLookup(context=None, connection=None)
        connection = None
        if row["connection_id"] is not None:
            connection = self._connection_from_row(row)
        return ConnectionLookup(
            context=self._workspace_context_from_row(row),
            connection=connection,
        )

    async def rename_connection(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        name: str,
        request_id: UUID,
        trace_id: str | None,
        authorize: ConnectionMutationAuthorizer,
    ) -> Connection:
        async with self._database.session() as session, session.begin():
            context = await self._mutation_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=connection_id,
                lock=True,
            )
            authorize(context)
            before = await self._fetch_connection(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
            )
            await session.execute(
                _RENAME_CONNECTION,
                {
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                    "name": name,
                },
            )
            await self._audit(
                session,
                context=context.workspace,
                user_id=user_id,
                auth_session_id=auth_session_id,
                connection_id=connection_id,
                name=name,
                action="CONNECTION_RENAMED",
                request_id=request_id,
                trace_id=trace_id,
                before={"name": before.name},
                after={"name": name},
            )
            renamed = await self._fetch_connection(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
            )
        return renamed

    async def get_draft_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> ConnectionDraftLookup:
        async with self._database.session() as session:
            context = await self._mutation_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=connection_id,
                lock=False,
            )
            result = await session.execute(
                _SELECT_DRAFT,
                {"workspace_id": workspace_id, "connection_id": connection_id},
            )
            row = result.mappings().one_or_none()
        return ConnectionDraftLookup(
            context=context,
            draft=self._draft_from_row(row) if row is not None else None,
        )

    async def put_draft(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        configuration: JsonObject,
        authorize: ConnectionMutationAuthorizer,
        compile_configuration: ConnectionDraftCompiler,
    ) -> ConnectionDraft:
        async with self._database.session() as session, session.begin():
            context = await self._mutation_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=connection_id,
                lock=True,
            )
            authorize(context)
            compiled = compile_configuration(context, configuration)
            result = await session.execute(
                _UPSERT_DRAFT,
                {
                    "connection_id": connection_id,
                    "workspace_id": workspace_id,
                    "draft_json": self._json(compiled),
                    "user_id": user_id,
                },
            )
            row = result.mappings().one()
        return self._draft_from_row(row)

    async def list_revisions_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        before_revision: int | None,
        limit: int,
    ) -> ConnectionRevisionPageLookup:
        async with self._database.session() as session:
            context = await self._mutation_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=connection_id,
                lock=False,
            )
            result = await session.execute(
                _LIST_REVISIONS,
                {
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                    "before_revision": before_revision,
                    "fetch_limit": limit + 1,
                },
            )
            rows = result.mappings().all()
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        return ConnectionRevisionPageLookup(
            context=context,
            page=ConnectionRevisionPage(
                items=tuple(self._revision_metadata_from_row(row) for row in visible_rows),
                next_before_revision=(
                    int(visible_rows[-1]["revision_number"]) if has_more and visible_rows else None
                ),
            ),
        )

    async def get_revision_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        revision_id: UUID,
    ) -> ConnectionRevisionLookup:
        async with self._database.session() as session:
            context = await self._mutation_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=connection_id,
                lock=False,
            )
            result = await session.execute(
                _GET_REVISION,
                {
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                    "revision_id": revision_id,
                },
            )
            row = result.mappings().one_or_none()
        return ConnectionRevisionLookup(
            context=context,
            revision=self._revision_from_row(row) if row is not None else None,
        )

    async def publish_revision(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        request_id: UUID,
        trace_id: str | None,
        authorize: ConnectionMutationAuthorizer,
        compile_configuration: ConnectionPublicationCompiler,
    ) -> ConnectionRevision:
        revision_id = uuid7()
        async with self._database.session() as session, session.begin():
            context = await self._mutation_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=connection_id,
                lock=True,
            )
            authorize(context)
            draft_result = await session.execute(
                _LOCK_DRAFT,
                {"workspace_id": workspace_id, "connection_id": connection_id},
            )
            draft_row = draft_result.mappings().one_or_none()
            if draft_row is None:
                raise ConnectionStateConflictError("connection draft does not exist")
            configuration = self._json_object(draft_row["draft_json"], "draft_json")
            compiled = compile_configuration(context, configuration)
            number_result = await session.execute(
                _NEXT_REVISION_NUMBER,
                {"connection_id": connection_id},
            )
            revision_number = number_result.scalar_one()
            if not isinstance(revision_number, int):
                raise TypeError("connection revision query returned invalid number")
            inserted = await session.execute(
                _INSERT_REVISION,
                {
                    "revision_id": revision_id,
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                    "revision_number": revision_number,
                    "definition_schema_version": compiled.definition_schema_version,
                    "config_json": self._json(compiled.configuration),
                    "config_hash": compiled.config_hash,
                    "user_id": user_id,
                },
            )
            row = inserted.mappings().one()
            await session.execute(
                _ACTIVATE_DRAFT_CONNECTION,
                {"workspace_id": workspace_id, "connection_id": connection_id},
            )
            connection = await self._fetch_connection(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
            )
            await self._audit(
                session,
                context=context.workspace,
                user_id=user_id,
                auth_session_id=auth_session_id,
                connection_id=connection_id,
                name=connection.name,
                action="CONNECTION_REVISION_PUBLISHED",
                request_id=request_id,
                trace_id=trace_id,
                after={
                    "config_hash": compiled.config_hash.hex(),
                    "definition_schema_version": compiled.definition_schema_version,
                    "revision_id": str(revision_id),
                    "revision_number": revision_number,
                    "status": connection.status.value,
                },
            )
        return self._revision_from_row(row)

    async def replace_access(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        access_policy: ConnectionAccessPolicy,
        request_id: UUID,
        trace_id: str | None,
        authorize: ConnectionMutationAuthorizer,
    ) -> Connection:
        async with self._database.session() as session, session.begin():
            context = await self._mutation_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=connection_id,
                lock=True,
            )
            authorize(context)
            before = await self._fetch_connection(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
            )
            await self._validate_projects(
                session,
                workspace_id=workspace_id,
                project_ids=access_policy.project_ids,
            )
            await session.execute(
                _DELETE_PROJECT_ACCESS,
                {"connection_id": connection_id},
            )
            await self._insert_project_access(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
                user_id=user_id,
                project_ids=access_policy.project_ids,
            )
            await session.execute(
                _UPDATE_ACCESS_MODE,
                {
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                    "access_mode": access_policy.mode.value,
                },
            )
            updated = await self._fetch_connection(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
            )
            await self._audit(
                session,
                context=context.workspace,
                user_id=user_id,
                auth_session_id=auth_session_id,
                connection_id=connection_id,
                name=updated.name,
                action="CONNECTION_ACCESS_UPDATED",
                request_id=request_id,
                trace_id=trace_id,
                before=self._access_json(before.access_policy),
                after=self._access_json(updated.access_policy),
            )
        return updated

    async def transition_lifecycle(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        action: ConnectionLifecycleAction,
        request_id: UUID,
        trace_id: str | None,
        authorize: ConnectionMutationAuthorizer,
    ) -> Connection:
        targets = {
            ConnectionLifecycleAction.DISABLE: ConnectionStatus.DISABLED,
            ConnectionLifecycleAction.ENABLE: ConnectionStatus.ACTIVE,
            ConnectionLifecycleAction.ARCHIVE: ConnectionStatus.ARCHIVED,
        }
        async with self._database.session() as session, session.begin():
            context = await self._mutation_context(
                session,
                user_id=user_id,
                workspace_id=workspace_id,
                connection_id=connection_id,
                lock=True,
            )
            authorize(context)
            target = targets[action]
            await session.execute(
                _UPDATE_LIFECYCLE,
                {
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                    "status": target.value,
                },
            )
            updated = await self._fetch_connection(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
            )
            await self._audit(
                session,
                context=context.workspace,
                user_id=user_id,
                auth_session_id=auth_session_id,
                connection_id=connection_id,
                name=updated.name,
                action=f"CONNECTION_{action.value}D"
                if action is not ConnectionLifecycleAction.DISABLE
                else "CONNECTION_DISABLED",
                request_id=request_id,
                trace_id=trace_id,
                before={"status": context.status.value},
                after={"status": target.value},
            )
        return updated

    async def _workspace_context(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        lock: bool,
    ) -> ConnectionWorkspaceContext:
        result = await session.execute(
            _LOCK_WORKSPACE_CONTEXT if lock else _READ_WORKSPACE_CONTEXT,
            {"user_id": user_id, "workspace_id": workspace_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ConnectionWorkspaceNotFoundError("workspace not found")
        return self._workspace_context_from_row(row)

    async def _mutation_context(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        lock: bool,
    ) -> ConnectionMutationContext:
        workspace = await self._workspace_context(
            session,
            user_id=user_id,
            workspace_id=workspace_id,
            lock=lock,
        )
        result = await session.execute(
            _LOCK_CONNECTION if lock else _READ_CONNECTION_CONTEXT,
            {"workspace_id": workspace_id, "connection_id": connection_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ConnectionNotFoundError("connection not found")
        return ConnectionMutationContext(
            workspace=workspace,
            connection_id=self._uuid_value(row["id"], "connection_id"),
            provider_key=self._string_value(row["provider_key"], "provider_key"),
            access_mode=ConnectionAccessMode(
                self._string_value(row["access_mode"], "access_mode"),
            ),
            status=ConnectionStatus(self._string_value(row["status"], "status")),
        )

    async def _validate_projects(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        project_ids: tuple[UUID, ...],
    ) -> None:
        if not project_ids:
            return
        result = await session.execute(
            _LOCK_SELECTED_PROJECTS,
            {"workspace_id": workspace_id, "project_ids": list(project_ids)},
        )
        found = {self._uuid_value(row[0], "project_id") for row in result.all()}
        if found != set(project_ids):
            raise ConnectionProjectNotFoundError("project not found")

    @staticmethod
    async def _insert_project_access(
        session: AsyncSession,
        *,
        workspace_id: UUID,
        connection_id: UUID,
        user_id: UUID,
        project_ids: tuple[UUID, ...],
    ) -> None:
        if not project_ids:
            return
        await session.execute(
            _INSERT_PROJECT_ACCESS,
            [
                {
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                    "project_id": project_id,
                    "user_id": user_id,
                }
                for project_id in project_ids
            ],
        )

    async def _fetch_connection(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> Connection:
        result = await session.execute(
            _SELECT_CONNECTION,
            {"workspace_id": workspace_id, "connection_id": connection_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ConnectionNotFoundError("connection not found")
        return self._connection_from_row(row)

    @staticmethod
    async def _audit(
        session: AsyncSession,
        *,
        context: ConnectionWorkspaceContext,
        user_id: UUID,
        auth_session_id: UUID,
        connection_id: UUID,
        name: str,
        action: str,
        request_id: UUID,
        trace_id: str | None,
        before: Mapping[str, object] | None = None,
        after: Mapping[str, object] | None = None,
        change: Mapping[str, object] | None = None,
    ) -> None:
        await session.execute(
            _INSERT_AUDIT,
            {
                "audit_id": uuid7(),
                "workspace_id": context.workspace_id,
                "user_id": user_id,
                "membership_role": context.role.value,
                "action": action,
                "connection_id": connection_id,
                "name": name,
                "before_json": json.dumps(before or {}, separators=(",", ":"), sort_keys=True),
                "after_json": json.dumps(after or {}, separators=(",", ":"), sort_keys=True),
                "change_json": json.dumps(change or {}, separators=(",", ":"), sort_keys=True),
                "request_id": str(request_id),
                "trace_id": trace_id,
                "session_id": str(auth_session_id),
            },
        )

    @classmethod
    def _workspace_context_from_row(cls, row: RowMapping) -> ConnectionWorkspaceContext:
        workspace_value = (
            row["authorized_workspace_id"]
            if "authorized_workspace_id" in row
            else row["workspace_id"]
        )
        return ConnectionWorkspaceContext(
            workspace_id=cls._uuid_value(workspace_value, "workspace_id"),
            status=ConnectionWorkspaceStatus(
                cls._string_value(row["workspace_status"], "workspace_status"),
            ),
            role=ConnectionAuthorizationRole(
                cls._string_value(row["membership_role"], "membership_role"),
            ),
        )

    @classmethod
    def _connection_from_row(cls, row: RowMapping) -> Connection:
        mode = ConnectionAccessMode(
            cls._string_value(row["connection_access_mode"], "connection_access_mode"),
        )
        project_values = cls._uuid_sequence(
            row["connection_project_ids"],
            "connection_project_ids",
        )
        if mode is ConnectionAccessMode.WORKSPACE and project_values:
            raise TypeError("WORKSPACE connection unexpectedly contains selected access")
        return Connection(
            connection_id=cls._uuid_value(row["connection_id"], "connection_id"),
            workspace_id=cls._uuid_value(
                row["connection_workspace_id"],
                "connection_workspace_id",
            ),
            name=cls._string_value(row["connection_name"], "connection_name"),
            provider_key=cls._string_value(
                row["connection_provider_key"],
                "connection_provider_key",
            ),
            access_policy=ConnectionAccessPolicy(
                mode=mode,
                project_ids=project_values,
            ),
            status=ConnectionStatus(
                cls._string_value(row["connection_status"], "connection_status"),
            ),
            created_at=cls._datetime_value(
                row["connection_created_at"],
                "connection_created_at",
            ),
            updated_at=cls._datetime_value(
                row["connection_updated_at"],
                "connection_updated_at",
            ),
            archived_at=cls._optional_datetime_value(
                row["connection_archived_at"],
                "connection_archived_at",
            ),
        )

    @classmethod
    def _draft_from_row(cls, row: RowMapping) -> ConnectionDraft:
        return ConnectionDraft(
            connection_id=cls._uuid_value(row["connection_id"], "connection_id"),
            workspace_id=cls._uuid_value(row["workspace_id"], "workspace_id"),
            configuration=cls._json_object(row["draft_json"], "draft_json"),
            updated_by_user_id=cls._optional_uuid_value(
                row["updated_by_user_id"],
                "updated_by_user_id",
            ),
            updated_at=cls._datetime_value(row["updated_at"], "updated_at"),
        )

    @classmethod
    def _revision_metadata_from_row(cls, row: RowMapping) -> ConnectionRevisionMetadata:
        number = row["revision_number"]
        schema_version = row["definition_schema_version"]
        if not isinstance(number, int) or not isinstance(schema_version, int):
            raise TypeError("connection revision query returned invalid version metadata")
        return ConnectionRevisionMetadata(
            revision_id=cls._uuid_value(row["id"], "revision_id"),
            connection_id=cls._uuid_value(row["connection_id"], "connection_id"),
            workspace_id=cls._uuid_value(row["workspace_id"], "workspace_id"),
            revision_number=number,
            definition_schema_version=schema_version,
            config_hash_hex=cls._string_value(row["config_hash_hex"], "config_hash_hex"),
            created_by_user_id=cls._optional_uuid_value(
                row["created_by_user_id"],
                "created_by_user_id",
            ),
            created_at=cls._datetime_value(row["created_at"], "created_at"),
        )

    @classmethod
    def _revision_from_row(cls, row: RowMapping) -> ConnectionRevision:
        return ConnectionRevision(
            metadata=cls._revision_metadata_from_row(row),
            configuration=cls._json_object(row["config_json"], "config_json"),
        )

    @staticmethod
    def _access_json(policy: ConnectionAccessPolicy) -> dict[str, object]:
        return {
            "access_mode": policy.mode.value,
            "project_ids": [str(item) for item in policy.project_ids],
        }

    @staticmethod
    def _json(value: Mapping[str, object]) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _json_object(value: object, field: str) -> JsonObject:
        if not isinstance(value, dict):
            raise TypeError(f"connection query returned invalid {field}")
        if not all(isinstance(key, str) for key in value):
            raise TypeError(f"connection query returned invalid {field}")
        return dict(value)

    @staticmethod
    def _uuid_sequence(value: object, field: str) -> tuple[UUID, ...]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise TypeError(f"connection query returned invalid {field}")
        items: list[UUID] = []
        for item in value:
            if not isinstance(item, UUID):
                raise TypeError(f"connection query returned invalid {field}")
            items.append(item)
        return tuple(items)

    @staticmethod
    def _uuid_value(value: object, field: str) -> UUID:
        if not isinstance(value, UUID):
            raise TypeError(f"connection query returned invalid {field}")
        return value

    @classmethod
    def _optional_uuid_value(cls, value: object, field: str) -> UUID | None:
        if value is None:
            return None
        return cls._uuid_value(value, field)

    @staticmethod
    def _string_value(value: object, field: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"connection query returned invalid {field}")
        return value

    @staticmethod
    def _datetime_value(value: object, field: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"connection query returned invalid {field}")
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
