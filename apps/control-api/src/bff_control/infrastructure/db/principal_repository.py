"""SQLAlchemy repository for durable control-plane principal admission."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from bff_control.domains.authentication.models import (
    AuthenticatedPrincipal,
    VerifiedAccessToken,
)
from bff_control.infrastructure.db.database import Database

_RESOLVE_ACTIVE_PRINCIPAL = text(
    """
    SELECT
        users.id AS user_id,
        auth_sessions.id AS auth_session_id,
        users.email AS email,
        users.display_name AS display_name
    FROM app.user_auth_identities AS identities
    JOIN app.users AS users
      ON users.id = identities.user_id
    JOIN app.auth_sessions AS auth_sessions
      ON auth_sessions.user_auth_identity_id = identities.id
    WHERE identities.issuer = :issuer
      AND identities.subject = :subject
      AND identities.status = 'ACTIVE'
      AND users.status = 'ACTIVE'
      AND auth_sessions.provider_session_id = :provider_session_id
      AND auth_sessions.revoked_at IS NULL
      AND auth_sessions.expires_at > CURRENT_TIMESTAMP
    """
)


class SqlAlchemyPrincipalRepository:
    """Resolve authentication evidence using the control-plane database."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def resolve_active_principal(
        self,
        token: VerifiedAccessToken,
    ) -> AuthenticatedPrincipal | None:
        """Resolve identity, user and local session admission in one DB snapshot."""

        async with self._database.session() as session:
            result = await session.execute(
                _RESOLVE_ACTIVE_PRINCIPAL,
                {
                    "issuer": token.issuer,
                    "subject": token.subject,
                    "provider_session_id": token.provider_session_id,
                },
            )
            row = result.mappings().one_or_none()

        if row is None:
            return None

        user_id = row["user_id"]
        auth_session_id = row["auth_session_id"]
        email = row["email"]
        display_name = row["display_name"]

        if not isinstance(user_id, UUID):
            raise TypeError("principal query returned a non-UUID user_id")
        if not isinstance(auth_session_id, UUID):
            raise TypeError("principal query returned a non-UUID auth_session_id")
        if not isinstance(email, str):
            raise TypeError("principal query returned a non-string email")
        if display_name is not None and not isinstance(display_name, str):
            raise TypeError("principal query returned an invalid display_name")

        return AuthenticatedPrincipal(
            user_id=user_id,
            auth_session_id=auth_session_id,
            email=email,
            display_name=display_name,
        )
