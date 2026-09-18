from __future__ import annotations

from pathlib import Path

from scripts.dev.doctor import Check, EnvFile, environment_checks, parse_env_file


def _messages(checks: list[Check]) -> list[str]:
    return [check.message for check in checks]


def _base_values() -> dict[str, str]:
    return {
        "POSTGRES_DB": "bff",
        "POSTGRES_USER": "bff",
        "POSTGRES_PASSWORD": "local-password",
        "BFF_DATABASE_URL": "postgresql+asyncpg://bff:pw@127.0.0.1:5432/bff",
        "BFF_MIGRATION_DATABASE_URL": "postgresql+psycopg://bff:pw@127.0.0.1:5432/bff",
        "RABBITMQ_DEFAULT_USER": "bff",
        "RABBITMQ_DEFAULT_PASS": "local-password",
        "RABBITMQ_DEFAULT_VHOST": "/",
        "VALKEY_PASSWORD": "local-password",
    }


def _env(values: dict[str, str]) -> EnvFile:
    return EnvFile(
        values=values,
        line_numbers={key: (index,) for index, key in enumerate(values, 1)},
        invalid_lines=(),
    )


def test_parse_env_file_reports_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "BFF_AUTH_CLIENT_ID=client_one\nBFF_AUTH_CLIENT_ID=client_two\n",
        encoding="utf-8",
    )

    env = parse_env_file(path)

    assert env.values["BFF_AUTH_CLIENT_ID"] == "client_two"
    assert env.line_numbers["BFF_AUTH_CLIENT_ID"] == (1, 2)
    checks = environment_checks(env, profile="base")
    assert any(check.level == "FAIL" for check in checks)
    assert any("duplicate .env key BFF_AUTH_CLIENT_ID" in message for message in _messages(checks))


def test_base_profile_warns_about_placeholders_without_requiring_auth() -> None:
    values = _base_values()
    values["BFF_AUTH_CLIENT_ID"] = "client_replace_me"

    checks = environment_checks(_env(values), profile="base")

    assert not any(check.level == "FAIL" for check in checks)
    assert any(check.level == "WARN" for check in checks)


def test_auth_profile_rejects_placeholder_or_inconsistent_workos_values() -> None:
    values = _base_values()
    values.update(
        {
            "BFF_AUTH_ISSUER": "https://api.workos.com/user_management/client_real",
            "BFF_AUTH_CLIENT_ID": "client_replace_me",
            "BFF_AUTH_JWKS_URL": "https://api.workos.com/sso/jwks/client_other",
            "BFF_WORKOS_API_KEY": "sk_replace_me",
        }
    )

    checks = environment_checks(_env(values), profile="auth")
    messages = _messages(checks)

    assert any(check.level == "FAIL" for check in checks)
    assert any("placeholder value(s) remain" in message for message in messages)
    assert any("BFF_AUTH_ISSUER must identify" in message for message in messages)
    assert any("BFF_AUTH_JWKS_URL must identify" in message for message in messages)


def test_auth_profile_accepts_consistent_workos_values() -> None:
    client_id = "client_01EXAMPLE"
    values = _base_values()
    values.update(
        {
            "BFF_AUTH_ISSUER": f"https://api.workos.com/user_management/{client_id}",
            "BFF_AUTH_CLIENT_ID": client_id,
            "BFF_AUTH_JWKS_URL": f"https://api.workos.com/sso/jwks/{client_id}",
            "BFF_WORKOS_API_KEY": "sk_test_example",
        }
    )

    checks = environment_checks(_env(values), profile="auth")

    assert not any(check.level == "FAIL" for check in checks)
