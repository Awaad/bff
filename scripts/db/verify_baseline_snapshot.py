#!/usr/bin/env python3
"""Verify immutable V2.1 SQL snapshots and the current role bootstrap."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CURRENT_SCHEMA = ROOT / "docs" / "schema" / "schema.sql"
BASELINE_SCHEMA = ROOT / "docs" / "schema" / "baselines" / "schema-v2.1.sql"
MIGRATION_SCHEMA = (
    ROOT / "apps" / "control-api" / "migrations" / "sql" / "0001_schema_baseline_v2_1.sql"
)
BASELINE_ROLES = ROOT / "docs" / "security" / "baselines" / "database-roles-v2.1.sql"
MIGRATION_ROLES = (
    ROOT / "apps" / "control-api" / "migrations" / "sql" / "0001_database_roles_v2_1.sql"
)
CURRENT_ROLES = ROOT / "docs" / "security" / "database-roles.sql"
APPLICATION_ROLES = ROOT / "apps" / "control-api" / "migrations" / "sql" / "application_roles.sql"


def schema_without_transaction_control(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip() not in {"BEGIN;", "COMMIT;"}]
    return "\n".join(lines).rstrip() + "\n"


def verify() -> list[str]:
    violations: list[str] = []

    expected_schema = schema_without_transaction_control(
        BASELINE_SCHEMA.read_text(encoding="utf-8"),
    )
    actual_schema = MIGRATION_SCHEMA.read_text(encoding="utf-8")

    if actual_schema != expected_schema:
        violations.append(
            "0001 schema migration drifted from retained V2.1 schema baseline",
        )

    expected_roles = BASELINE_ROLES.read_text(encoding="utf-8")
    actual_roles = MIGRATION_ROLES.read_text(encoding="utf-8")

    if actual_roles != expected_roles:
        violations.append(
            "0001 role bootstrap drifted from retained V2.1 role baseline",
        )

    current_roles = CURRENT_ROLES.read_text(encoding="utf-8")
    application_roles = APPLICATION_ROLES.read_text(encoding="utf-8")

    if application_roles != current_roles:
        violations.append(
            "deployable application role bootstrap drifted from docs/security/database-roles.sql",
        )

    return violations


def main() -> int:
    violations = verify()
    for violation in violations:
        print(violation)

    if violations:
        return 1

    print("immutable V2.1 snapshots and current application roles are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
