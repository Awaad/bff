"""Create Schema Baseline V2.1.

Revision ID: 0001_schema_baseline_v2_1
Revises:
Create Date: 2026-09-14
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001_schema_baseline_v2_1"
down_revision = None
branch_labels = None
depends_on = None

_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "0001_schema_baseline_v2_1.sql"


def upgrade() -> None:
    """Apply the reviewed V2.1 PostgreSQL schema atomically."""

    sql = _SQL_PATH.read_text(encoding="utf-8")
    bind = op.get_bind()

    # psycopg supports non-parameterized multi-statement execution. The SQL
    # asset deliberately contains no BEGIN/COMMIT; Alembic owns the transaction.
    bind.exec_driver_sql(sql)

    # The baseline sets app,public so unqualified application DDL resolves to app.
    # Restore public before Alembic writes its own version table row.
    bind.exec_driver_sql("SET search_path TO public")


def downgrade() -> None:
    """Baseline downgrade is intentionally unsupported once data exists."""

    raise RuntimeError(
        "Schema Baseline V2.1 is irreversible; restore a disposable database "
        "or roll forward with a corrective migration",
    )
