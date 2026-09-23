"""Control-plane composition root."""

from fastapi import FastAPI

from bff_control.api.app import create_app
from bff_control.api.contracts import ApplicationResources
from bff_control.core.settings import (
    get_application_settings,
    get_authentication_settings,
    get_database_settings,
    get_workos_settings,
)
from bff_control.domains.authentication.provisioning import SessionProvisioningService
from bff_control.domains.authentication.service import AuthenticationService
from bff_control.domains.projects.service import ProjectService
from bff_control.domains.workspaces.service import WorkspaceService
from bff_control.infrastructure.auth.workos import WorkOSAccessTokenVerifier
from bff_control.infrastructure.auth.workos_profile import WorkOSUserProfileClient
from bff_control.infrastructure.db.database import Database
from bff_control.infrastructure.db.principal_repository import (
    SqlAlchemyPrincipalRepository,
)
from bff_control.infrastructure.db.project_repository import SqlAlchemyProjectRepository
from bff_control.infrastructure.db.session_provisioning_repository import (
    SqlAlchemySessionProvisioningRepository,
)
from bff_control.infrastructure.db.workspace_repository import SqlAlchemyWorkspaceRepository
from bff_control.infrastructure.observability.telemetry import configure_telemetry


def _resource_factory() -> ApplicationResources:
    database = Database(get_database_settings())
    authentication_settings = get_authentication_settings()
    verifier = WorkOSAccessTokenVerifier(authentication_settings)

    principal_repository = SqlAlchemyPrincipalRepository(database)
    authenticator = AuthenticationService(verifier, principal_repository)

    provisioning_repository = SqlAlchemySessionProvisioningRepository(database)
    profile_provider = WorkOSUserProfileClient(get_workos_settings())
    session_provisioner = SessionProvisioningService(
        verifier,
        provisioning_repository,
        profile_provider,
        absolute_ttl_seconds=authentication_settings.session_absolute_ttl_seconds,
    )

    workspace_repository = SqlAlchemyWorkspaceRepository(database)
    workspace_service = WorkspaceService(workspace_repository)

    project_repository = SqlAlchemyProjectRepository(database)
    project_service = ProjectService(project_repository)

    telemetry = configure_telemetry(get_application_settings())

    return ApplicationResources(
        database=database,
        telemetry=telemetry,
        authenticator=authenticator,
        session_provisioner=session_provisioner,
        workspace_service=workspace_service,
        project_service=project_service,
    )


def create_application() -> FastAPI:
    """Wire the HTTP transport to concrete process infrastructure."""

    return create_app(resource_factory=_resource_factory)
