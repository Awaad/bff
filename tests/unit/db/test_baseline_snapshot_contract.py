from __future__ import annotations

from scripts.db.verify_baseline_snapshot import (
    APPLICATION_ROLES,
    BASELINE_ROLES,
    BASELINE_SCHEMA,
    CURRENT_ROLES,
    CURRENT_SCHEMA,
    MIGRATION_ROLES,
    MIGRATION_SCHEMA,
    schema_without_transaction_control,
    verify,
)


def test_immutable_v2_1_assets_still_match_retained_baselines() -> None:
    assert MIGRATION_SCHEMA.read_text(encoding="utf-8") == schema_without_transaction_control(
        BASELINE_SCHEMA.read_text(encoding="utf-8"),
    )
    assert MIGRATION_ROLES.read_text(encoding="utf-8") == BASELINE_ROLES.read_text(
        encoding="utf-8",
    )


def test_living_schema_has_evolved_past_v2_1_baseline() -> None:
    current = CURRENT_SCHEMA.read_text(encoding="utf-8")
    baseline = BASELINE_SCHEMA.read_text(encoding="utf-8")

    assert "CREATE TABLE user_auth_identities" in current
    assert "CREATE TABLE user_auth_identities" not in baseline


def test_current_role_document_matches_deployable_bootstrap() -> None:
    assert CURRENT_ROLES.read_text(encoding="utf-8") == APPLICATION_ROLES.read_text(
        encoding="utf-8",
    )


def test_baseline_verifier_is_green() -> None:
    assert verify() == []
