"""Connection application service."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from bff_control.domains.connections.contracts import (
    ConnectionConfigurationInvalidError,
    ConnectionNotFoundError,
    ConnectionPermissionDeniedError,
    ConnectionRepository,
    ConnectionStateConflictError,
    ConnectionWorkspaceNotActiveError,
    ConnectionWorkspaceNotFoundError,
)
from bff_control.domains.connections.models import (
    Connection,
    ConnectionAccessPolicy,
    ConnectionDraft,
    ConnectionLifecycleAction,
    ConnectionMutationContext,
    ConnectionPage,
    ConnectionPageCursor,
    ConnectionRevision,
    ConnectionRevisionPage,
    ConnectionWorkspaceContext,
    PublishedConnectionConfiguration,
)
from bff_control.domains.connections.policies import (
    can_author_connections,
    can_create_with_access,
    can_manage_connection_lifecycle,
    can_read_connections,
    can_replace_access,
    connection_allows_access_replacement,
    connection_allows_authoring,
    lifecycle_transition_allowed,
    normalize_access_policy,
    normalize_connection_name,
    normalize_draft_configuration,
    normalize_provider_key,
    validate_before_revision,
    validate_connection_page_limit,
    validate_connection_revision_page_limit,
    workspace_allows_connection_mutation,
    workspace_allows_lifecycle_action,
)
from bff_control.domains.connections.providers import (
    ConnectionProviderRegistry,
    ProviderConfigurationError,
)


class ConnectionService:
    """Enforce Connection authorization, lifecycle, and provider policy."""

    def __init__(
        self,
        repository: ConnectionRepository,
        provider_registry: ConnectionProviderRegistry,
    ) -> None:
        self._repository = repository
        self._providers = provider_registry

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
    ) -> Connection:
        normalized_name = normalize_connection_name(name)
        normalized_provider = normalize_provider_key(provider_key)
        normalized_access = normalize_access_policy(
            access_policy.mode,
            access_policy.project_ids,
        )
        try:
            self._providers.require(normalized_provider)
        except ProviderConfigurationError as exc:
            raise ConnectionConfigurationInvalidError(str(exc)) from exc
        return await self._repository.create_connection(
            user_id=user_id,
            auth_session_id=auth_session_id,
            workspace_id=workspace_id,
            name=normalized_name,
            provider_key=normalized_provider,
            access_policy=normalized_access,
            request_id=request_id,
            trace_id=trace_id,
            authorize=lambda context: self._authorize_creation(
                context,
                normalized_access,
            ),
        )

    async def list_connections(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        cursor: ConnectionPageCursor | None,
        limit: int,
    ) -> ConnectionPage:
        lookup = await self._repository.list_for_user(
            user_id=user_id,
            workspace_id=workspace_id,
            cursor=cursor,
            limit=validate_connection_page_limit(limit),
        )
        self._authorize_read(lookup.context)
        return lookup.page

    async def get_connection(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> Connection:
        lookup = await self._repository.get_for_user(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
        )
        self._authorize_read(lookup.context)
        if lookup.connection is None:
            raise ConnectionNotFoundError("connection not found")
        return lookup.connection

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
    ) -> Connection:
        return await self._repository.rename_connection(
            user_id=user_id,
            auth_session_id=auth_session_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            name=normalize_connection_name(name),
            request_id=request_id,
            trace_id=trace_id,
            authorize=self._authorize_authoring,
        )

    async def get_draft(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> ConnectionDraft:
        lookup = await self._repository.get_draft_for_user(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
        )
        if lookup.context is None:
            raise ConnectionWorkspaceNotFoundError("workspace not found")
        self._authorize_authoring(lookup.context)
        if lookup.draft is None:
            raise ConnectionStateConflictError("connection draft does not exist")
        return lookup.draft

    async def put_draft(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        configuration: Mapping[str, object],
    ) -> ConnectionDraft:
        normalized = normalize_draft_configuration(configuration)
        return await self._repository.put_draft(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            configuration=normalized,
            authorize=self._authorize_authoring,
            compile_configuration=self._compile_draft,
        )

    async def list_revisions(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        before_revision: int | None,
        limit: int,
    ) -> ConnectionRevisionPage:
        lookup = await self._repository.list_revisions_for_user(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            before_revision=validate_before_revision(before_revision),
            limit=validate_connection_revision_page_limit(limit),
        )
        self._authorize_read_mutation_context(lookup.context)
        return lookup.page

    async def get_revision(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        revision_id: UUID,
    ) -> ConnectionRevision:
        lookup = await self._repository.get_revision_for_user(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            revision_id=revision_id,
        )
        if lookup.context is None:
            raise ConnectionWorkspaceNotFoundError("workspace not found")
        if not can_author_connections(lookup.context.workspace.role):
            raise ConnectionPermissionDeniedError(
                "connection configuration read is not permitted",
            )
        if lookup.revision is None:
            raise ConnectionNotFoundError("connection revision not found")
        return lookup.revision

    async def publish_revision(
        self,
        *,
        user_id: UUID,
        auth_session_id: UUID,
        workspace_id: UUID,
        connection_id: UUID,
        request_id: UUID,
        trace_id: str | None,
    ) -> ConnectionRevision:
        return await self._repository.publish_revision(
            user_id=user_id,
            auth_session_id=auth_session_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            request_id=request_id,
            trace_id=trace_id,
            authorize=self._authorize_authoring,
            compile_configuration=self._compile_publication,
        )

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
    ) -> Connection:
        normalized = normalize_access_policy(
            access_policy.mode,
            access_policy.project_ids,
        )
        return await self._repository.replace_access(
            user_id=user_id,
            auth_session_id=auth_session_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            access_policy=normalized,
            request_id=request_id,
            trace_id=trace_id,
            authorize=lambda context: self._authorize_access(context, normalized),
        )

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
    ) -> Connection:
        return await self._repository.transition_lifecycle(
            user_id=user_id,
            auth_session_id=auth_session_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            action=action,
            request_id=request_id,
            trace_id=trace_id,
            authorize=lambda context: self._authorize_lifecycle(context, action),
        )

    @staticmethod
    def _authorize_read(context: ConnectionWorkspaceContext | None) -> None:
        if context is None or not can_read_connections(context.role):
            raise ConnectionWorkspaceNotFoundError("workspace not found")

    @staticmethod
    def _authorize_read_mutation_context(
        context: ConnectionMutationContext | None,
    ) -> None:
        if context is None:
            raise ConnectionWorkspaceNotFoundError("workspace not found")
        if not can_read_connections(context.workspace.role):
            raise ConnectionWorkspaceNotFoundError("workspace not found")

    @staticmethod
    def _authorize_creation(
        context: ConnectionWorkspaceContext,
        access_policy: ConnectionAccessPolicy,
    ) -> None:
        if not can_create_with_access(context.role, access_policy.mode):
            raise ConnectionPermissionDeniedError("connection creation is not permitted")
        if not workspace_allows_connection_mutation(context.status):
            raise ConnectionWorkspaceNotActiveError(
                "workspace lifecycle does not allow connection creation",
            )

    @staticmethod
    def _authorize_authoring(context: ConnectionMutationContext) -> None:
        if not can_author_connections(context.workspace.role):
            raise ConnectionPermissionDeniedError("connection authoring is not permitted")
        if not workspace_allows_connection_mutation(context.workspace.status):
            raise ConnectionWorkspaceNotActiveError(
                "workspace lifecycle does not allow connection authoring",
            )
        if not connection_allows_authoring(context.status):
            raise ConnectionStateConflictError(
                "connection lifecycle does not allow authoring",
            )

    def _compile_publication(
        self,
        context: ConnectionMutationContext,
        configuration: Mapping[str, object],
    ) -> PublishedConnectionConfiguration:
        try:
            return self._providers.publish(context.provider_key, configuration)
        except ProviderConfigurationError as exc:
            raise ConnectionConfigurationInvalidError(str(exc)) from exc

    def _compile_draft(
        self,
        context: ConnectionMutationContext,
        configuration: Mapping[str, object],
    ) -> dict[str, object]:
        try:
            return self._providers.compile_draft(
                context.provider_key,
                configuration,
            )
        except ProviderConfigurationError as exc:
            raise ConnectionConfigurationInvalidError(str(exc)) from exc

    @staticmethod
    def _authorize_access(
        context: ConnectionMutationContext,
        access_policy: ConnectionAccessPolicy,
    ) -> None:
        if not can_replace_access(
            context.workspace.role,
            context.access_mode,
            access_policy.mode,
        ):
            raise ConnectionPermissionDeniedError(
                "connection access management is not permitted",
            )
        if not workspace_allows_connection_mutation(context.workspace.status):
            raise ConnectionWorkspaceNotActiveError(
                "workspace lifecycle does not allow connection access changes",
            )
        if not connection_allows_access_replacement(context.status):
            raise ConnectionStateConflictError(
                "connection lifecycle does not allow access changes",
            )

    @staticmethod
    def _authorize_lifecycle(
        context: ConnectionMutationContext,
        action: ConnectionLifecycleAction,
    ) -> None:
        if not can_manage_connection_lifecycle(context.workspace.role):
            raise ConnectionPermissionDeniedError(
                "connection lifecycle management is not permitted",
            )
        if not workspace_allows_lifecycle_action(context.workspace.status, action):
            raise ConnectionWorkspaceNotActiveError(
                "workspace lifecycle does not allow this connection transition",
            )
        if not lifecycle_transition_allowed(context.status, action):
            raise ConnectionStateConflictError(
                "connection lifecycle transition is not permitted",
            )
