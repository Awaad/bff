"""Add the Workspace-scoped Project pagination index.

Revision ID: 0004_project_pagination
Revises: 0003_auth_sessions
Create Date: 2026-09-21
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0004_project_pagination"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None

_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "0004_project_pagination.sql"


def upgrade() -> None:
    """Add the index used by deterministic Project cursor pagination."""

    bind = op.get_bind()
    bind.exec_driver_sql(_SQL_PATH.read_text(encoding="utf-8"))


def downgrade() -> None:
    """Remove the additive Project pagination index."""

    op.drop_index(
        "idx_projects_workspace_created_id",
        table_name="projects",
        schema="app",
    )
