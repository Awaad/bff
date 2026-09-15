#!/usr/bin/env python3
"""Apply PostgreSQL application roles and grants for Schema Baseline V2.1."""

from __future__ import annotations

from pathlib import Path

from bff_control.core.settings import get_database_settings
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
ROLES_SQL = (
    ROOT
    / "apps"
    / "control-api"
    / "migrations"
    / "sql"
    / "0001_database_roles_v2_1.sql"
)


def main() -> int:
    settings = get_database_settings()
    engine = create_engine(
        settings.migration_database_url.get_secret_value(),
        pool_pre_ping=True,
    )

    try:
        sql = ROLES_SQL.read_text(encoding="utf-8")
        with engine.begin() as connection:
            connection.exec_driver_sql(sql)
    finally:
        engine.dispose()

    print("database application roles/grants applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
