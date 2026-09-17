"""Add durable control-plane session admission state.

Revision ID: 0003_auth_sessions
Revises: 0002_user_auth_identities
Create Date: 2026-09-17
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0003_auth_sessions"
down_revision = "0002_user_auth_identities"
branch_labels = None
depends_on = None

_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "0003_auth_sessions.sql"


def upgrade() -> None:
    """Add durable local authentication-session admission state."""

    bind = op.get_bind()
    bind.exec_driver_sql(_SQL_PATH.read_text(encoding="utf-8"))


def downgrade() -> None:
    """Do not silently destroy authentication-session security history."""

    raise RuntimeError(
        "0003_auth_sessions is security-history-bearing and intentionally irreversible; "
        "roll forward with a corrective migration",
    )
