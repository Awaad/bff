"""SQLAlchemy repository for durable session provisioning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bff_control.core.ids import uuid7
from bff_control.domains.authentication.models import (
    AuthenticatedPrincipal,
    VerifiedAccessToken,
)
from bff_control.domains.authentication.provisioning_contracts import (
    AccountLinkRequiredError,
    SessionProvisioningAuthenticationError,
)
from bff_control.domains.authentication.provisioning_models import (
    ExternalUserProfile,
    ProvisionedSession,
    ProvisioningIdentity,
)
from bff_control.infrastructure.db.database import Database


class _IdentityRace(Exception):
    """Internal savepoint signal used to roll back an orphan candidate User."""


@dataclass(frozen=True, slots=True)
class _ActiveIdentity:
    identity_id: UUID
    user_id: UUID
    email: str
    display_name: str | None


_FIND_IDENTITY = text(
    """
    SELECT
        identities.id AS identity_id,
        users.id AS user_id,
        identities.status AS identity_status,
        users.status AS user_status
    FROM app.user_auth_identities AS identities
    JOIN app.users AS users ON users.id = identities.user_id
    WHERE identities.issuer = :issuer
      AND identities.subject = :subject
    """
)

_LOCK_ACTIVE_IDENTITY = text(
    """
    SELECT
        identities.id AS identity_id,
        users.id AS user_id,
        users.email AS email,
        users.display_name AS display_name
    FROM app.user_auth_identities AS identities
    JOIN app.users AS users ON users.id = identities.user_id
    WHERE identities.id = :identity_id
      AND identities.issuer = :issuer
      AND identities.subject = :subject
      AND identities.status = 'ACTIVE'
      AND users.status = 'ACTIVE'
    FOR SHARE OF identities, users
    """
)

_FIND_EXACT_IDENTITY = text(
    """
    SELECT
        identities.id AS identity_id,
        users.id AS user_id,
        identities.status AS identity_status,
        users.status AS user_status,
        users.email AS email,
        users.display_name AS display_name
    FROM app.user_auth_identities AS identities
    JOIN app.users AS users ON users.id = identities.user_id
    WHERE identities.issuer = :issuer
      AND identities.subject = :subject
    """
)

_INSERT_USER = text(
    """
    INSERT INTO app.users (
        id,
        email,
        email_normalized,
        display_name
    ) VALUES (
        :id,
        :email,
        :email_normalized,
        :display_name
    )
    ON CONFLICT (email_normalized) DO NOTHING
    RETURNING id
    """
)

_INSERT_IDENTITY = text(
    """
    INSERT INTO app.user_auth_identities (
        id,
        user_id,
        issuer,
        subject
    ) VALUES (
        :id,
        :user_id,
        :issuer,
        :subject
    )
    ON CONFLICT (issuer, subject) DO NOTHING
    RETURNING id
    """
)

_INSERT_SESSION = text(
    """
    INSERT INTO app.auth_sessions (
        id,
        user_auth_identity_id,
        provider_session_id,
        expires_at
    ) VALUES (
        :id,
        :identity_id,
        :provider_session_id,
        CURRENT_TIMESTAMP + (:ttl_seconds * INTERVAL '1 second')
    )
    ON CONFLICT (user_auth_identity_id, provider_session_id) DO NOTHING
    RETURNING id, expires_at
    """
)

_FIND_SESSION = text(
    """
    SELECT
        id,
        expires_at,
        revoked_at,
        expires_at > CURRENT_TIMESTAMP AS unexpired
    FROM app.auth_sessions
    WHERE user_auth_identity_id = :identity_id
      AND provider_session_id = :provider_session_id
    FOR SHARE
    """
)

_INSERT_AUDIT = text(
    """
    INSERT INTO app.audit_events (
        id,
        scope,
        actor_type,
        actor_user_id,
        effective_user_id,
        action,
        outcome,
        resource_type,
        resource_id,
        session_id,
        surface
    ) VALUES (
        :id,
        'PLATFORM',
        'USER',
        :user_id,
        :user_id,
        'AUTH_SESSION_CREATED',
        'SUCCEEDED',
        'AUTH_SESSION',
        :session_id,
        :session_id_text,
        'PUBLIC_API'
    )
    """
)


class SqlAlchemySessionProvisioningRepository:
    """Create or reuse local identity/session admission under DB uniqueness rules."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def find_identity(
        self,
        token: VerifiedAccessToken,
    ) -> ProvisioningIdentity | None:
        async with self._database.session() as session:
            result = await session.execute(
                _FIND_IDENTITY,
                {"issuer": token.issuer, "subject": token.subject},
            )
            row = result.mappings().one_or_none()

        if row is None:
            return None

        return ProvisioningIdentity(
            identity_id=self._uuid_value(row["identity_id"], "identity_id"),
            user_id=self._uuid_value(row["user_id"], "user_id"),
            active=(
                row["identity_status"] == "ACTIVE"
                and row["user_status"] == "ACTIVE"
            ),
        )

    async def admit_existing_identity(
        self,
        token: VerifiedAccessToken,
        identity: ProvisioningIdentity,
        *,
        ttl_seconds: int,
    ) -> ProvisionedSession:
        async with self._database.session() as session:
            async with session.begin():
                active = await self._lock_active_identity(
                    session,
                    token,
                    identity.identity_id,
                )
                return await self._admit_session(
                    session,
                    token,
                    active,
                    ttl_seconds=ttl_seconds,
                )

    async def provision_new_identity(
        self,
        token: VerifiedAccessToken,
        profile: ExternalUserProfile,
        *,
        ttl_seconds: int,
    ) -> ProvisionedSession:
        async with self._database.session() as session:
            async with session.begin():
                existing = await self._find_exact_identity(session, token)
                if existing is not None:
                    active = self._require_active(existing)
                    return await self._admit_session(
                        session,
                        token,
                        active,
                        ttl_seconds=ttl_seconds,
                    )

                active = await self._create_identity_or_resolve_race(
                    session,
                    token,
                    profile,
                )
                return await self._admit_session(
                    session,
                    token,
                    active,
                    ttl_seconds=ttl_seconds,
                )

    async def _create_identity_or_resolve_race(
        self,
        session: AsyncSession,
        token: VerifiedAccessToken,
        profile: ExternalUserProfile,
    ) -> _ActiveIdentity:
        email = profile.email.strip()
        email_normalized = email.casefold()

        if not email or not email_normalized:
            raise ValueError("provider email must be non-empty")

        try:
            async with session.begin_nested():
                user_id = uuid7()
                inserted_user = await session.execute(
                    _INSERT_USER,
                    {
                        "id": user_id,
                        "email": email,
                        "email_normalized": email_normalized,
                        "display_name": profile.display_name,
                    },
                )
                if inserted_user.scalar_one_or_none() is None:
                    existing = await self._find_exact_identity(session, token)
                    if existing is not None:
                        return self._require_active(existing)
                    raise AccountLinkRequiredError("account linking required")

                identity_id = uuid7()
                inserted_identity = await session.execute(
                    _INSERT_IDENTITY,
                    {
                        "id": identity_id,
                        "user_id": user_id,
                        "issuer": token.issuer,
                        "subject": token.subject,
                    },
                )
                if inserted_identity.scalar_one_or_none() is None:
                    raise _IdentityRace

                return _ActiveIdentity(
                    identity_id=identity_id,
                    user_id=user_id,
                    email=email,
                    display_name=profile.display_name,
                )
        except _IdentityRace:
            existing = await self._find_exact_identity(session, token)
            if existing is None:
                raise RuntimeError(
                    "identity uniqueness race resolved without identity row",
                )
            return self._require_active(existing)

    async def _lock_active_identity(
        self,
        session: AsyncSession,
        token: VerifiedAccessToken,
        identity_id: UUID,
    ) -> _ActiveIdentity:
        result = await session.execute(
            _LOCK_ACTIVE_IDENTITY,
            {
                "identity_id": identity_id,
                "issuer": token.issuer,
                "subject": token.subject,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise SessionProvisioningAuthenticationError(
                "session provisioning authentication failed",
            )
        return self._active_identity_from_row(row)

    async def _find_exact_identity(
        self,
        session: AsyncSession,
        token: VerifiedAccessToken,
    ) -> Mapping[str, object] | None:
        result = await session.execute(
            _FIND_EXACT_IDENTITY,
            {"issuer": token.issuer, "subject": token.subject},
        )
        return result.mappings().one_or_none()

    def _require_active(
        self,
        row: Mapping[str, object],
    ) -> _ActiveIdentity:
        if row["identity_status"] != "ACTIVE" or row["user_status"] != "ACTIVE":
            raise SessionProvisioningAuthenticationError(
                "session provisioning authentication failed",
            )
        return self._active_identity_from_row(row)

    async def _admit_session(
        self,
        session: AsyncSession,
        token: VerifiedAccessToken,
        identity: _ActiveIdentity,
        *,
        ttl_seconds: int,
    ) -> ProvisionedSession:
        session_id = uuid7()
        inserted = await session.execute(
            _INSERT_SESSION,
            {
                "id": session_id,
                "identity_id": identity.identity_id,
                "provider_session_id": token.provider_session_id,
                "ttl_seconds": ttl_seconds,
            },
        )
        inserted_row = inserted.mappings().one_or_none()

        if inserted_row is not None:
            expires_at = self._datetime_value(
                inserted_row["expires_at"],
                "expires_at",
            )
            await session.execute(
                _INSERT_AUDIT,
                {
                    "id": uuid7(),
                    "user_id": identity.user_id,
                    "session_id": session_id,
                    "session_id_text": str(session_id),
                },
            )
            return ProvisionedSession(
                principal=self._principal(identity, session_id),
                expires_at=expires_at,
                created=True,
            )

        existing = await session.execute(
            _FIND_SESSION,
            {
                "identity_id": identity.identity_id,
                "provider_session_id": token.provider_session_id,
            },
        )
        row = existing.mappings().one()

        if row["revoked_at"] is not None or row["unexpired"] is not True:
            raise SessionProvisioningAuthenticationError(
                "session provisioning authentication failed",
            )

        existing_session_id = self._uuid_value(row["id"], "session_id")
        expires_at = self._datetime_value(row["expires_at"], "expires_at")
        return ProvisionedSession(
            principal=self._principal(identity, existing_session_id),
            expires_at=expires_at,
            created=False,
        )

    @staticmethod
    def _principal(
        identity: _ActiveIdentity,
        session_id: UUID,
    ) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            user_id=identity.user_id,
            auth_session_id=session_id,
            email=identity.email,
            display_name=identity.display_name,
        )

    @staticmethod
    def _active_identity_from_row(
        row: Mapping[str, object],
    ) -> _ActiveIdentity:
        return _ActiveIdentity(
            identity_id=SqlAlchemySessionProvisioningRepository._uuid_value(
                row["identity_id"],
                "identity_id",
            ),
            user_id=SqlAlchemySessionProvisioningRepository._uuid_value(
                row["user_id"],
                "user_id",
            ),
            email=SqlAlchemySessionProvisioningRepository._string_value(
                row["email"],
                "email",
            ),
            display_name=SqlAlchemySessionProvisioningRepository._optional_string(
                row["display_name"],
                "display_name",
            ),
        )

    @staticmethod
    def _uuid_value(value: object, field: str) -> UUID:
        if not isinstance(value, UUID):
            raise TypeError(f"session provisioning query returned invalid {field}")
        return value

    @staticmethod
    def _datetime_value(value: object, field: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"session provisioning query returned invalid {field}")
        return value

    @staticmethod
    def _string_value(value: object, field: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"session provisioning query returned invalid {field}")
        return value

    @staticmethod
    def _optional_string(value: object, field: str) -> str | None:
        if value is not None and not isinstance(value, str):
            raise TypeError(f"session provisioning query returned invalid {field}")
        return value
