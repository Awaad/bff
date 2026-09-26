"""Harden the initial Connection control-plane access path.

Revision ID: 0005_connection_control_plane
Revises: 0004_project_pagination
Create Date: 2026-09-24
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0005_connection_control_plane"
down_revision = "0004_project_pagination"
branch_labels = None
depends_on = None

_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "0005_connection_control_plane.sql"


def upgrade() -> None:
    """Add the index used by deterministic Connection cursor pagination."""

    bind = op.get_bind()
    bind.exec_driver_sql(_SQL_PATH.read_text(encoding="utf-8"))


def downgrade() -> None:
    """Remove the additive Connection pagination index."""

    op.drop_index(
        "idx_connections_workspace_created_id",
        table_name="connections",
        schema="app",
    )
