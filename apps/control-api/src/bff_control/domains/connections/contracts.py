"""Connection domain interfaces."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol
from uuid import UUID

from bff_control.domains.connections.models import (
    Connection,
    ConnectionAccessPolicy,
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
    ConnectionRevisionPage,
    ConnectionRevisionPageLookup,
    ConnectionWorkspaceContext,
    JsonObject,
    PublishedConnectionConfiguration,
)


class ConnectionWorkspaceNotFoundError(Exception):
    """Raised when the parent Workspace is absent or hidden from the principal."""


class ConnectionNotFoundError(Exception):
    """Raised when a Connection is absent or outside the authorized Workspace."""


class ConnectionProjectNotFoundError(Exception):
    """Raised when selected Project access cannot be resolved in the Workspace."""


class ConnectionPermissionDeniedError(Exception):
    """Raised when the active Workspace role lacks a Connection permission."""


class ConnectionWorkspaceNotActiveError(Exception):
    """Raised when Workspace lifecycle blocks a Connection mutation."""


class ConnectionStateConflictError(Exception):
    """Raised when Connection lifecycle blocks a requested mutation."""


class ConnectionConfigurationInvalidError(Exception):
    """Raised when provider configuration cannot be accepted."""


ConnectionCreationAuthorizer = Callable[[ConnectionWorkspaceContext], None]
ConnectionMutationAuthorizer = Callable[[ConnectionMutationContext], None]
ConnectionDraftCompiler = Callable[
    [ConnectionMutationContext, Mapping[str, object]],
    JsonObject,
]
ConnectionPublicationCompiler = Callable[
    [ConnectionMutationContext, Mapping[str, object]],
    PublishedConnectionConfiguration,
]


class ConnectionRepository(Protocol):
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
    ) -> Connection: ...

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ConnectionPageCursor | None,
        limit: int,
    ) -> ConnectionPageLookup: ...

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> ConnectionLookup: ...

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
    ) -> Connection: ...

    async def get_draft_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> ConnectionDraftLookup: ...

    async def put_draft(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        configuration: JsonObject,
        authorize: ConnectionMutationAuthorizer,
        compile_configuration: ConnectionDraftCompiler,
    ) -> ConnectionDraft: ...

    async def list_revisions_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        before_revision: int | None,
        limit: int,
    ) -> ConnectionRevisionPageLookup: ...

    async def get_revision_for_user(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        revision_id: UUID,
    ) -> ConnectionRevisionLookup: ...

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
    ) -> ConnectionRevision: ...

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
    ) -> Connection: ...

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
    ) -> Connection: ...


class ConnectionManager(Protocol):
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
    ) -> Connection: ...

    async def list_connections(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ConnectionPageCursor | None,
        limit: int,
    ) -> ConnectionPage: ...

    async def get_connection(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> Connection: ...

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
    ) -> Connection: ...

    async def get_draft(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> ConnectionDraft: ...

    async def put_draft(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        configuration: Mapping[str, object],
    ) -> ConnectionDraft: ...

    async def list_revisions(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        before_revision: int | None,
        limit: int,
    ) -> ConnectionRevisionPage: ...

    async def get_revision(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        revision_id: UUID,
    ) -> ConnectionRevision: ...

    async def publish_revision(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        request_id: UUID,
        trace_id: str | None,
    ) -> ConnectionRevision: ...

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
    ) -> Connection: ...

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
    ) -> Connection: ...
