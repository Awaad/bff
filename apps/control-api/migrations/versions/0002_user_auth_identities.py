"""Add provider-neutral user authentication identities.

Revision ID: 0002_user_auth_identities
Revises: 0001_schema_baseline_v2_1
Create Date: 2026-09-16
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0002_user_auth_identities"
down_revision = "0001_schema_baseline_v2_1"
branch_labels = None
depends_on = None

_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "0002_user_auth_identities.sql"


def upgrade() -> None:
    """Add durable external authentication identity mapping and ACL hardening."""

    bind = op.get_bind()
    bind.exec_driver_sql(_SQL_PATH.read_text(encoding="utf-8"))


def downgrade() -> None:
    """Do not silently destroy authentication identity history."""

    raise RuntimeError(
        "0002_user_auth_identities is data-bearing and intentionally irreversible; "
        "roll forward with a corrective migration",
    )
