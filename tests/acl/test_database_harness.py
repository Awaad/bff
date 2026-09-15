from __future__ import annotations

import secrets

import psycopg
import pytest

import tests.support.database as database_support
from tests.support.database import DatabaseTestEnvironment


def test_partial_login_role_provisioning_cleans_created_roles(
    postgres_test_db: DatabaseTestEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = f"cleanup_{secrets.token_hex(4)}"
    missing_group_role = f"bff_missing_group_{suffix}"
    login_roles = (
        f"bff_test_valid_{suffix}",
        f"bff_test_broken_{suffix}",
    )

    monkeypatch.setattr(
        database_support,
        "GROUP_ROLES",
        {
            "valid": "bff_control_writer",
            "broken": missing_group_role,
        },
    )

    admin_url = database_support._required_admin_url()

    with pytest.raises(psycopg.errors.UndefinedObject):
        database_support._create_login_principals(
            admin_url,
            postgres_test_db.owner_url,
            suffix,
        )

    with psycopg.connect(
        database_support._postgres_dsn(admin_url),
        autocommit=True,
    ) as connection:
        rows = connection.execute(
            "SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)",
            login_roles,
        ).fetchall()

    assert rows == []
