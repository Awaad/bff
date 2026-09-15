from __future__ import annotations
from uuid import UUID

import psycopg
import pytest
from psycopg import Connection

from tests.support.database import IDS


def _execution_values(
    *,
    execution_id: str,
    public_ref: str,
    project_id: str | None = None,
    lineage_mode: str = "BINDING",
    binding_id: str | None = IDS["binding_public"],
    binding_revision_id: str | None = IDS["binding_revision_public"],
    operation_version_id: str = IDS["operation_version_1"],
    connection_id: str = IDS["connection_1"],
    connection_revision_id: str = IDS["connection_revision_1"],
    credential_id: str = IDS["credential_1"],
    credential_revision_id: str = IDS["credential_revision_1"],
) -> dict[str, str | None]:
    return {
        "id": execution_id,
        "public_ref": public_ref,
        "workspace_id": IDS["workspace_1"],
        "project_id": project_id or IDS["project_1"],
        "lineage_mode": lineage_mode,
        "binding_id": binding_id,
        "binding_revision_id": binding_revision_id,
        "operation_id": IDS["operation_1"],
        "operation_version_id": operation_version_id,
        "connection_id": connection_id,
        "connection_revision_id": connection_revision_id,
        "credential_id": credential_id,
        "credential_revision_id": credential_revision_id,
    }


def _insert_execution(
    connection: Connection[tuple[object, ...]],
    values: dict[str, str | None],
) -> None:
    connection.execute(
        """
        INSERT INTO app.executions (
            id,
            public_execution_ref,
            workspace_id,
            project_id,
            lineage_mode,
            binding_id,
            binding_revision_id,
            operation_id,
            operation_version_id,
            connection_id,
            connection_revision_id,
            credential_id,
            credential_revision_id,
            source,
            status
        ) VALUES (
            %(id)s,
            %(public_ref)s,
            %(workspace_id)s,
            %(project_id)s,
            %(lineage_mode)s,
            %(binding_id)s,
            %(binding_revision_id)s,
            %(operation_id)s,
            %(operation_version_id)s,
            %(connection_id)s,
            %(connection_revision_id)s,
            %(credential_id)s,
            %(credential_revision_id)s,
            'INTERNAL',
            'PENDING'
        )
        """,
        values,
    )


def test_binding_execution_cannot_claim_wrong_project(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    values = _execution_values(
        execution_id="00000000-0000-7000-8000-000000001001",
        public_ref="schema_wrong_project",
        project_id=IDS["project_2"],
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert_execution(owner_db, values)


def test_binding_execution_cannot_substitute_operation_version(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    values = _execution_values(
        execution_id="00000000-0000-7000-8000-000000001002",
        public_ref="schema_wrong_operation_version",
        operation_version_id=IDS["operation_version_2"],
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert_execution(owner_db, values)


def test_binding_execution_requires_binding_id_with_revision(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    values = _execution_values(
        execution_id="00000000-0000-7000-8000-000000001003",
        public_ref="schema_partial_binding_lineage",
        binding_id=None,
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_execution(owner_db, values)


def test_direct_execution_cannot_smuggle_binding_lineage(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    values = _execution_values(
        execution_id="00000000-0000-7000-8000-000000001004",
        public_ref="schema_direct_binding_dodge",
        lineage_mode="DIRECT",
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_execution(owner_db, values)


def test_direct_execution_cannot_mix_connection_and_credential_graphs(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    values = _execution_values(
        execution_id="00000000-0000-7000-8000-000000001005",
        public_ref="schema_direct_mixed_graph",
        lineage_mode="DIRECT",
        binding_id=None,
        binding_revision_id=None,
        credential_id=IDS["credential_2"],
        credential_revision_id=IDS["credential_revision_2"],
    )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert_execution(owner_db, values)


def test_internal_binding_cannot_receive_public_identifier(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        owner_db.execute(
            """
            INSERT INTO app.binding_public_identifiers (
                id,
                workspace_id,
                project_id,
                binding_id,
                public_id
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                "00000000-0000-7000-8000-000000001011",
                IDS["workspace_1"],
                IDS["project_1"],
                IDS["binding_internal"],
                "internal-must-not-be-public",
            ),
        )


def test_public_binding_can_receive_public_identifier(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    owner_db.execute(
        """
        INSERT INTO app.binding_public_identifiers (
            id,
            workspace_id,
            project_id,
            binding_id,
            public_id
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            "00000000-0000-7000-8000-000000001012",
            IDS["workspace_1"],
            IDS["project_1"],
            IDS["binding_public"],
            "public-positive-control",
        ),
    )

    row = owner_db.execute(
        """
        SELECT binding_id
        FROM app.binding_public_identifiers
        WHERE public_id = 'public-positive-control'
        """,
    ).fetchone()

    assert row == (UUID(IDS["binding_public"]),)


def test_sync_run_rejects_revision_without_binding_id(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        owner_db.execute(
            """
            INSERT INTO app.sync_runs (
                id,
                workspace_id,
                project_id,
                sync_definition_id,
                sync_revision_id,
                trigger,
                scan_mode,
                execution_mode,
                status,
                source_binding_revision_id
            ) VALUES (%s, %s, %s, %s, %s, 'MANUAL', 'FULL', 'DRY_RUN', 'PENDING', %s)
            """,
            (
                "00000000-0000-7000-8000-000000001021",
                IDS["workspace_1"],
                IDS["project_1"],
                IDS["sync_definition"],
                IDS["sync_revision"],
                IDS["binding_revision_public"],
            ),
        )


def test_framer_active_link_requires_ownership_proof(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        owner_db.execute(
            """
            INSERT INTO app.framer_project_links (
                id,
                workspace_id,
                project_id,
                framer_authorization_id,
                framer_project_id,
                status
            ) VALUES (%s, %s, %s, %s, %s, 'ACTIVE')
            """,
            (
                "00000000-0000-7000-8000-000000001031",
                IDS["workspace_1"],
                IDS["project_1"],
                IDS["framer_auth_1"],
                "framer-no-proof",
            ),
        )


def test_two_tenants_can_hold_same_pending_framer_project_id(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    external_id = "framer-pending-shared"

    owner_db.execute(
        """
        INSERT INTO app.framer_project_links (
            id,
            workspace_id,
            project_id,
            framer_authorization_id,
            framer_project_id,
            status
        ) VALUES
            (%s, %s, %s, %s, %s, 'PENDING_VERIFICATION'),
            (%s, %s, %s, %s, %s, 'PENDING_VERIFICATION')
        """,
        (
            "00000000-0000-7000-8000-000000001032",
            IDS["workspace_1"],
            IDS["project_1"],
            IDS["framer_auth_1"],
            external_id,
            "00000000-0000-7000-8000-000000001033",
            IDS["workspace_2"],
            IDS["project_3"],
            IDS["framer_auth_2"],
            external_id,
        ),
    )


def test_verified_active_framer_link_reserves_external_project_id_globally(
    owner_db: Connection[tuple[object, ...]],
) -> None:
    external_id = "framer-active-reservation"
    first_id = "00000000-0000-7000-8000-000000001034"
    second_id = "00000000-0000-7000-8000-000000001035"

    owner_db.execute(
        """
        INSERT INTO app.framer_project_links (
            id,
            workspace_id,
            project_id,
            framer_authorization_id,
            framer_project_id,
            status
        ) VALUES
            (%s, %s, %s, %s, %s, 'PENDING_VERIFICATION'),
            (%s, %s, %s, %s, %s, 'PENDING_VERIFICATION')
        """,
        (
            first_id,
            IDS["workspace_1"],
            IDS["project_1"],
            IDS["framer_auth_1"],
            external_id,
            second_id,
            IDS["workspace_2"],
            IDS["project_3"],
            IDS["framer_auth_2"],
            external_id,
        ),
    )

    owner_db.execute(
        """
        UPDATE app.framer_project_links
        SET
            status = 'ACTIVE',
            ownership_verified_at = now(),
            ownership_verification_method = 'SERVER_API'
        WHERE id = %s
        """,
        (first_id,),
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        owner_db.execute(
            """
            UPDATE app.framer_project_links
            SET
                status = 'ACTIVE',
                ownership_verified_at = now(),
                ownership_verification_method = 'SERVER_API'
            WHERE id = %s
            """,
            (second_id,),
        )
