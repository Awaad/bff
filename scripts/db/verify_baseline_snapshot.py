#!/usr/bin/env python3
"""Verify immutable migration SQL assets match the accepted V2.1 specifications."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CANONICAL_SCHEMA = ROOT / "docs" / "schema" / "schema.sql"
MIGRATION_SCHEMA = (
    ROOT / "apps" / "control-api" / "migrations" / "sql" / "0001_schema_baseline_v2_1.sql"
)
CANONICAL_ROLES = ROOT / "docs" / "security" / "database-roles.sql"
MIGRATION_ROLES = (
    ROOT / "apps" / "control-api" / "migrations" / "sql" / "0001_database_roles_v2_1.sql"
)


def canonical_schema_without_transaction_control(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip() not in {"BEGIN;", "COMMIT;"}]
    return "\n".join(lines).rstrip() + "\n"


def verify() -> list[str]:
    violations: list[str] = []

    expected_schema = canonical_schema_without_transaction_control(
        CANONICAL_SCHEMA.read_text(encoding="utf-8"),
    )
    actual_schema = MIGRATION_SCHEMA.read_text(encoding="utf-8")

    if actual_schema != expected_schema:
        violations.append(
            "baseline migration SQL drifted from docs/schema/schema.sql",
        )

    expected_roles = CANONICAL_ROLES.read_text(encoding="utf-8")
    actual_roles = MIGRATION_ROLES.read_text(encoding="utf-8")

    if actual_roles != expected_roles:
        violations.append(
            "database role bootstrap SQL drifted from docs/security/database-roles.sql",
        )

    return violations


def main() -> int:
    violations = verify()
    for violation in violations:
        print(violation)

    if violations:
        return 1

    print("baseline migration assets match accepted V2.1 specifications")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
