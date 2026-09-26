from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
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
    ConnectionAccessMode,
    ConnectionAccessPolicy,
    ConnectionAuthorizationRole,
    ConnectionDraft,
    ConnectionDraftLookup,
    ConnectionLifecycleAction,
    ConnectionLookup,
    ConnectionMutationContext,
    ConnectionPage,
    ConnectionPageLookup,
    ConnectionRevision,
    ConnectionRevisionLookup,
    ConnectionRevisionMetadata,
    ConnectionRevisionPage,
    ConnectionRevisionPageLookup,
    ConnectionStatus,
    ConnectionWorkspaceContext,
    ConnectionWorkspaceStatus,
)
from bff_control.domains.connections.providers import ConnectionProviderRegistry
from bff_control.domains.connections.service import ConnectionService

USER_ID = UUID("00000000-0000-7000-8000-000000002001")
SESSION_ID = UUID("00000000-0000-7000-8000-000000002002")
WORKSPACE_ID = UUID("00000000-0000-7000-8000-000000002003")
CONNECTION_ID = UUID("00000000-0000-7000-8000-000000002004")
PROJECT_ID = UUID("00000000-0000-7000-8000-000000002005")
REVISION_ID = UUID("00000000-0000-7000-8000-000000002006")
REQUEST_ID = UUID("00000000-0000-7000-8000-000000002007")
NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


def _workspace_context(
    *,
    role: ConnectionAuthorizationRole = ConnectionAuthorizationRole.BUILDER,
    status: ConnectionWorkspaceStatus = ConnectionWorkspaceStatus.ACTIVE,
) -> ConnectionWorkspaceContext:
    return ConnectionWorkspaceContext(
        workspace_id=WORKSPACE_ID,
        role=role,
        status=status,
    )


def _mutation_context(
    *,
    role: ConnectionAuthorizationRole = ConnectionAuthorizationRole.BUILDER,
    workspace_status: ConnectionWorkspaceStatus = ConnectionWorkspaceStatus.ACTIVE,
    connection_status: ConnectionStatus = ConnectionStatus.DRAFT,
    access_mode: ConnectionAccessMode = ConnectionAccessMode.SELECTED_PROJECTS,
) -> ConnectionMutationContext:
    return ConnectionMutationContext(
        workspace=_workspace_context(role=role, status=workspace_status),
        connection_id=CONNECTION_ID,
        provider_key="generic_http",
        access_mode=access_mode,
        status=connection_status,
    )


def _connection(
    *,
    status: ConnectionStatus = ConnectionStatus.DRAFT,
    mode: ConnectionAccessMode = ConnectionAccessMode.SELECTED_PROJECTS,
) -> Connection:
    return Connection(
        connection_id=CONNECTION_ID,
        workspace_id=WORKSPACE_ID,
        name="Primary API",
        provider_key="generic_http",
        access_policy=ConnectionAccessPolicy(mode=mode, project_ids=(PROJECT_ID,)),
        status=status,
        created_at=NOW,
        updated_at=NOW,
        archived_at=None,
    )


def _draft() -> ConnectionDraft:
    return ConnectionDraft(
        connection_id=CONNECTION_ID,
        workspace_id=WORKSPACE_ID,
        configuration={"base_url": "https://api.example.com"},
        updated_by_user_id=USER_ID,
        updated_at=NOW,
    )


def _revision() -> ConnectionRevision:
    return ConnectionRevision(
        metadata=ConnectionRevisionMetadata(
            revision_id=REVISION_ID,
            connection_id=CONNECTION_ID,
            workspace_id=WORKSPACE_ID,
            revision_number=1,
            definition_schema_version=1,
            config_hash_hex="00" * 32,
            created_by_user_id=USER_ID,
            created_at=NOW,
        ),
        configuration={"base_url": "https://api.example.com"},
    )


class FakeConnectionRepository:
    def __init__(self) -> None:
        self.workspace_context = _workspace_context()
        self.mutation_context = _mutation_context()
        self.connection = _connection()
        self.created: dict[str, object] | None = None
        self.published_configuration: dict[str, object] | None = None
        self.revision_list_arguments: dict[str, object] | None = None

    async def create_connection(self, **kwargs: object) -> Connection:
        authorize = kwargs["authorize"]
        assert callable(authorize)
        authorize(self.workspace_context)
        self.created = kwargs
        return self.connection

    async def list_for_user(self, **kwargs: object) -> ConnectionPageLookup:
        del kwargs
        return ConnectionPageLookup(
            context=self.workspace_context,
            page=ConnectionPage(items=(self.connection,), next_cursor=None),
        )

    async def get_for_user(self, **kwargs: object) -> ConnectionLookup:
        del kwargs
        return ConnectionLookup(
            context=self.workspace_context,
            connection=self.connection,
        )

    async def rename_connection(self, **kwargs: object) -> Connection:
        authorize = kwargs["authorize"]
        assert callable(authorize)
        authorize(self.mutation_context)
        return self.connection

    async def get_draft_for_user(self, **kwargs: object) -> ConnectionDraftLookup:
        del kwargs
        return ConnectionDraftLookup(context=self.mutation_context, draft=_draft())

    async def put_draft(self, **kwargs: object) -> ConnectionDraft:
        authorize = kwargs["authorize"]
        assert callable(authorize)
        authorize(self.mutation_context)
        compiler = kwargs["compile_configuration"]
        assert callable(compiler)
        configuration = kwargs["configuration"]
        assert isinstance(configuration, dict)
        compiled = compiler(self.mutation_context, configuration)
        return ConnectionDraft(
            connection_id=CONNECTION_ID,
            workspace_id=WORKSPACE_ID,
            configuration=compiled,
            updated_by_user_id=USER_ID,
            updated_at=NOW,
        )

    async def list_revisions_for_user(
        self,
        **kwargs: object,
    ) -> ConnectionRevisionPageLookup:
        self.revision_list_arguments = kwargs
        return ConnectionRevisionPageLookup(
            context=self.mutation_context,
            page=ConnectionRevisionPage(
                items=(_revision().metadata,),
                next_before_revision=None,
            ),
        )

    async def get_revision_for_user(self, **kwargs: object) -> ConnectionRevisionLookup:
        del kwargs
        return ConnectionRevisionLookup(
            context=self.mutation_context,
            revision=_revision(),
        )

    async def publish_revision(self, **kwargs: object) -> ConnectionRevision:
        authorize = kwargs["authorize"]
        assert callable(authorize)
        authorize(self.mutation_context)
        compiler = kwargs["compile_configuration"]
        assert callable(compiler)
        compiled = compiler(
            self.mutation_context,
            {"base_url": "HTTPS://API.EXAMPLE.COM/"},
        )
        self.published_configuration = compiled.configuration
        return _revision()

    async def replace_access(self, **kwargs: object) -> Connection:
        authorize = kwargs["authorize"]
        assert callable(authorize)
        authorize(self.mutation_context)
        return self.connection

    async def transition_lifecycle(self, **kwargs: object) -> Connection:
        authorize = kwargs["authorize"]
        assert callable(authorize)
        authorize(self.mutation_context)
        return self.connection


def _service(repository: FakeConnectionRepository) -> ConnectionService:
    return ConnectionService(
        cast(ConnectionRepository, repository),
        ConnectionProviderRegistry.default(),
    )


@pytest.mark.asyncio
async def test_builder_creates_selected_connection_with_normalized_identity() -> None:
    repository = FakeConnectionRepository()
    service = _service(repository)

    result = await service.create_connection(
        user_id=USER_ID,
        auth_session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        name="  Primary API  ",
        provider_key="generic_http",
        access_policy=ConnectionAccessPolicy(
            mode=ConnectionAccessMode.SELECTED_PROJECTS,
            project_ids=(PROJECT_ID,),
        ),
        request_id=REQUEST_ID,
        trace_id="trace",
    )

    assert result is repository.connection
    assert repository.created is not None
    assert repository.created["name"] == "Primary API"


@pytest.mark.asyncio
async def test_builder_cannot_create_workspace_wide_connection() -> None:
    repository = FakeConnectionRepository()
    service = _service(repository)

    with pytest.raises(ConnectionPermissionDeniedError):
        await service.create_connection(
            user_id=USER_ID,
            auth_session_id=SESSION_ID,
            workspace_id=WORKSPACE_ID,
            name="Primary API",
            provider_key="generic_http",
            access_policy=ConnectionAccessPolicy(
                mode=ConnectionAccessMode.WORKSPACE,
                project_ids=(),
            ),
            request_id=REQUEST_ID,
            trace_id=None,
        )


@pytest.mark.asyncio
async def test_owner_can_create_workspace_wide_connection() -> None:
    repository = FakeConnectionRepository()
    repository.workspace_context = _workspace_context(
        role=ConnectionAuthorizationRole.OWNER,
    )
    service = _service(repository)

    await service.create_connection(
        user_id=USER_ID,
        auth_session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        name="Primary API",
        provider_key="generic_http",
        access_policy=ConnectionAccessPolicy(
            mode=ConnectionAccessMode.WORKSPACE,
            project_ids=(),
        ),
        request_id=REQUEST_ID,
        trace_id=None,
    )

    assert repository.created is not None


@pytest.mark.asyncio
async def test_viewer_can_read_but_cannot_author() -> None:
    repository = FakeConnectionRepository()
    repository.workspace_context = _workspace_context(
        role=ConnectionAuthorizationRole.VIEWER,
    )
    repository.mutation_context = _mutation_context(
        role=ConnectionAuthorizationRole.VIEWER,
    )
    service = _service(repository)

    assert (
        await service.get_connection(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            connection_id=CONNECTION_ID,
        )
        is repository.connection
    )
    with pytest.raises(ConnectionPermissionDeniedError):
        await service.put_draft(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            connection_id=CONNECTION_ID,
            configuration={"base_url": "https://api.example.com"},
        )


@pytest.mark.asyncio
async def test_draft_write_rejects_unknown_fields_and_canonicalizes_provider_state() -> None:
    repository = FakeConnectionRepository()
    service = _service(repository)

    draft = await service.put_draft(
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        connection_id=CONNECTION_ID,
        configuration={"base_url": "HTTPS://API.EXAMPLE.COM/v1/"},
    )

    assert draft.configuration == {"base_url": "https://api.example.com/v1"}
    with pytest.raises(ConnectionConfigurationInvalidError):
        await service.put_draft(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            connection_id=CONNECTION_ID,
            configuration={"base_url": "https://api.example.com", "api_key": "secret"},
        )


@pytest.mark.asyncio
async def test_builder_can_replace_selected_access_but_not_change_mode() -> None:
    repository = FakeConnectionRepository()
    service = _service(repository)

    await service.replace_access(
        user_id=USER_ID,
        auth_session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        connection_id=CONNECTION_ID,
        access_policy=ConnectionAccessPolicy(
            mode=ConnectionAccessMode.SELECTED_PROJECTS,
            project_ids=(),
        ),
        request_id=REQUEST_ID,
        trace_id=None,
    )

    with pytest.raises(ConnectionPermissionDeniedError):
        await service.replace_access(
            user_id=USER_ID,
            auth_session_id=SESSION_ID,
            workspace_id=WORKSPACE_ID,
            connection_id=CONNECTION_ID,
            access_policy=ConnectionAccessPolicy(
                mode=ConnectionAccessMode.WORKSPACE,
                project_ids=(),
            ),
            request_id=REQUEST_ID,
            trace_id=None,
        )


@pytest.mark.asyncio
async def test_revision_history_passes_bounded_keyset_page_to_repository() -> None:
    repository = FakeConnectionRepository()
    service = _service(repository)

    page = await service.list_revisions(
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        connection_id=CONNECTION_ID,
        before_revision=12,
        limit=5,
    )

    assert page.items == (_revision().metadata,)
    assert repository.revision_list_arguments is not None
    assert repository.revision_list_arguments["before_revision"] == 12
    assert repository.revision_list_arguments["limit"] == 5


@pytest.mark.asyncio
async def test_publication_canonicalizes_provider_configuration() -> None:
    repository = FakeConnectionRepository()
    service = _service(repository)

    await service.publish_revision(
        user_id=USER_ID,
        auth_session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        connection_id=CONNECTION_ID,
        request_id=REQUEST_ID,
        trace_id=None,
    )

    assert repository.published_configuration == {
        "base_url": "https://api.example.com",
    }


@pytest.mark.asyncio
async def test_archived_connection_rejects_authoring() -> None:
    repository = FakeConnectionRepository()
    repository.mutation_context = _mutation_context(
        connection_status=ConnectionStatus.ARCHIVED,
    )
    service = _service(repository)

    with pytest.raises(ConnectionStateConflictError):
        await service.put_draft(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            connection_id=CONNECTION_ID,
            configuration={"base_url": "https://api.example.com"},
        )


@pytest.mark.asyncio
async def test_only_owner_or_admin_can_manage_lifecycle() -> None:
    repository = FakeConnectionRepository()
    repository.mutation_context = _mutation_context(
        connection_status=ConnectionStatus.ACTIVE,
    )
    service = _service(repository)

    with pytest.raises(ConnectionPermissionDeniedError):
        await service.transition_lifecycle(
            user_id=USER_ID,
            auth_session_id=SESSION_ID,
            workspace_id=WORKSPACE_ID,
            connection_id=CONNECTION_ID,
            action=ConnectionLifecycleAction.DISABLE,
            request_id=REQUEST_ID,
            trace_id=None,
        )


@pytest.mark.asyncio
async def test_suspended_workspace_allows_disable_but_blocks_enable() -> None:
    repository = FakeConnectionRepository()
    repository.mutation_context = _mutation_context(
        role=ConnectionAuthorizationRole.ADMIN,
        workspace_status=ConnectionWorkspaceStatus.SUSPENDED,
        connection_status=ConnectionStatus.ACTIVE,
    )
    service = _service(repository)

    await service.transition_lifecycle(
        user_id=USER_ID,
        auth_session_id=SESSION_ID,
        workspace_id=WORKSPACE_ID,
        connection_id=CONNECTION_ID,
        action=ConnectionLifecycleAction.DISABLE,
        request_id=REQUEST_ID,
        trace_id=None,
    )

    repository.mutation_context = _mutation_context(
        role=ConnectionAuthorizationRole.ADMIN,
        workspace_status=ConnectionWorkspaceStatus.SUSPENDED,
        connection_status=ConnectionStatus.DISABLED,
    )
    with pytest.raises(ConnectionWorkspaceNotActiveError):
        await service.transition_lifecycle(
            user_id=USER_ID,
            auth_session_id=SESSION_ID,
            workspace_id=WORKSPACE_ID,
            connection_id=CONNECTION_ID,
            action=ConnectionLifecycleAction.ENABLE,
            request_id=REQUEST_ID,
            trace_id=None,
        )


@pytest.mark.asyncio
async def test_connection_reads_preserve_existence_hiding() -> None:
    repository = FakeConnectionRepository()
    repository.workspace_context = None  # type: ignore[assignment]
    service = _service(repository)

    with pytest.raises(ConnectionWorkspaceNotFoundError):
        await service.list_connections(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            cursor=None,
            limit=50,
        )

    repository.workspace_context = _workspace_context()
    repository.connection = None  # type: ignore[assignment]
    with pytest.raises(ConnectionNotFoundError):
        await service.get_connection(
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            connection_id=CONNECTION_ID,
        )
