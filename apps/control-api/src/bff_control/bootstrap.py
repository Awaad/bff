"""Control-plane composition root."""

from fastapi import FastAPI

from bff_control.api.app import create_app
from bff_control.api.contracts import ApplicationResources
from bff_control.core.settings import (
    get_application_settings,
    get_authentication_settings,
    get_database_settings,
)
from bff_control.domains.authentication.service import AuthenticationService
from bff_control.infrastructure.auth.workos import WorkOSAccessTokenVerifier
from bff_control.infrastructure.db.database import Database
from bff_control.infrastructure.db.principal_repository import (
    SqlAlchemyPrincipalRepository,
)
from bff_control.infrastructure.observability.telemetry import configure_telemetry


def _resource_factory() -> ApplicationResources:
    database = Database(get_database_settings())
    verifier = WorkOSAccessTokenVerifier(get_authentication_settings())
    repository = SqlAlchemyPrincipalRepository(database)
    authenticator = AuthenticationService(verifier, repository)
    telemetry = configure_telemetry(get_application_settings())

    return ApplicationResources(
        database=database,
        telemetry=telemetry,
        authenticator=authenticator,
    )


def create_application() -> FastAPI:
    """Wire the HTTP transport to concrete process infrastructure."""

    return create_app(resource_factory=_resource_factory)
