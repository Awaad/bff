#!/usr/bin/env python3
"""Validate the local BFF development environment without exposing secrets."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

ROOT: Final = Path(__file__).resolve().parents[2]
ENV_PATH: Final = ROOT / ".env"
_KEY_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLACEHOLDER_MARKERS: Final = (
    "replace_me",
    "********",
    "<real value>",
    "<real_value>",
)
BASE_REQUIRED_KEYS: Final = (
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "BFF_DATABASE_URL",
    "BFF_MIGRATION_DATABASE_URL",
    "RABBITMQ_DEFAULT_USER",
    "RABBITMQ_DEFAULT_PASS",
    "RABBITMQ_DEFAULT_VHOST",
    "VALKEY_PASSWORD",
)
AUTH_REQUIRED_KEYS: Final = (
    "BFF_AUTH_ISSUER",
    "BFF_AUTH_CLIENT_ID",
    "BFF_AUTH_JWKS_URL",
    "BFF_WORKOS_API_KEY",
)


@dataclass(frozen=True, slots=True)
class EnvFile:
    values: dict[str, str]
    line_numbers: dict[str, tuple[int, ...]]
    invalid_lines: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Check:
    level: str
    message: str


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_env_file(path: Path) -> EnvFile:
    """Parse enough dotenv syntax to detect unsafe local configuration drift."""

    values: dict[str, str] = {}
    line_numbers: dict[str, list[int]] = {}
    invalid_lines: list[int] = []

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            invalid_lines.append(line_number)
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            invalid_lines.append(line_number)
            continue

        line_numbers.setdefault(key, []).append(line_number)
        values[key] = _unquote(raw_value)

    return EnvFile(
        values=values,
        line_numbers={key: tuple(lines) for key, lines in line_numbers.items()},
        invalid_lines=tuple(invalid_lines),
    )


def _is_placeholder(value: str) -> bool:
    lowered = value.casefold()
    return any(marker.casefold() in lowered for marker in PLACEHOLDER_MARKERS)


def _required_key_checks(env: EnvFile, required: tuple[str, ...]) -> list[Check]:
    checks: list[Check] = []
    for key in required:
        value = env.values.get(key)
        if value is None or not value.strip():
            checks.append(Check("FAIL", f"missing required environment key {key}"))
    return checks


def environment_checks(env: EnvFile, *, profile: str) -> list[Check]:
    """Validate deterministic local environment invariants without printing values."""

    checks: list[Check] = []

    if env.invalid_lines:
        rendered = ", ".join(str(line) for line in env.invalid_lines)
        checks.append(Check("FAIL", f"invalid .env syntax on line(s): {rendered}"))

    for key, lines in sorted(env.line_numbers.items()):
        if len(lines) > 1:
            rendered = ", ".join(str(line) for line in lines)
            checks.append(Check("FAIL", f"duplicate .env key {key} on lines {rendered}"))

    checks.extend(_required_key_checks(env, BASE_REQUIRED_KEYS))

    runtime_url = env.values.get("BFF_DATABASE_URL", "")
    if runtime_url and not runtime_url.startswith("postgresql+asyncpg://"):
        checks.append(Check("FAIL", "BFF_DATABASE_URL must use postgresql+asyncpg"))

    migration_url = env.values.get("BFF_MIGRATION_DATABASE_URL", "")
    if migration_url and not migration_url.startswith("postgresql+psycopg://"):
        checks.append(Check("FAIL", "BFF_MIGRATION_DATABASE_URL must use postgresql+psycopg"))

    placeholder_keys = sorted(key for key, value in env.values.items() if _is_placeholder(value))
    if placeholder_keys:
        rendered = ", ".join(placeholder_keys)
        level = "FAIL" if profile == "auth" else "WARN"
        checks.append(Check(level, f"placeholder value(s) remain in: {rendered}"))

    if profile != "auth":
        return checks

    checks.extend(_required_key_checks(env, AUTH_REQUIRED_KEYS))
    client_id = env.values.get("BFF_AUTH_CLIENT_ID", "")
    issuer = env.values.get("BFF_AUTH_ISSUER", "")
    jwks_url = env.values.get("BFF_AUTH_JWKS_URL", "")
    api_key = env.values.get("BFF_WORKOS_API_KEY", "")

    if client_id and not client_id.startswith("client_"):
        checks.append(Check("FAIL", "BFF_AUTH_CLIENT_ID must be a WorkOS client ID"))

    if issuer:
        parsed = urlsplit(issuer)
        if parsed.scheme != "https" or not parsed.netloc:
            checks.append(Check("FAIL", "BFF_AUTH_ISSUER must be an HTTPS URL"))
        if client_id and client_id not in issuer:
            checks.append(Check("FAIL", "BFF_AUTH_ISSUER must identify the configured client ID"))

    if jwks_url:
        parsed = urlsplit(jwks_url)
        if parsed.scheme != "https" or not parsed.netloc:
            checks.append(Check("FAIL", "BFF_AUTH_JWKS_URL must be an HTTPS URL"))
        if client_id and client_id not in jwks_url:
            checks.append(Check("FAIL", "BFF_AUTH_JWKS_URL must identify the configured client ID"))

    if api_key and not api_key.startswith(("sk_test_", "sk_live_")):
        checks.append(Check("FAIL", "BFF_WORKOS_API_KEY has an unexpected prefix"))

    return checks


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _tool_check(executable: str, command: list[str]) -> Check:
    if shutil.which(executable) is None:
        return Check("FAIL", f"required tool is not on PATH: {executable}")
    result = _run(command)
    if result.returncode != 0:
        return Check("FAIL", f"required tool command failed: {' '.join(command)}")
    return Check("PASS", f"tool available: {executable}")


def _version_checks() -> list[Check]:
    checks: list[Check] = []
    expected_python = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    actual_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if actual_python != expected_python:
        checks.append(
            Check(
                "FAIL",
                f"Python {actual_python} is active; repository requires {expected_python}",
            )
        )
    else:
        checks.append(Check("PASS", f"Python version matches {expected_python}"))

    checks.extend(
        [
            _tool_check("uv", ["uv", "--version"]),
            _tool_check("node", ["node", "--version"]),
            _tool_check("pnpm", ["pnpm", "--version"]),
            _tool_check("docker", ["docker", "compose", "version"]),
        ]
    )

    if shutil.which("node") is not None:
        expected_node = (ROOT / ".node-version").read_text(encoding="utf-8").strip()
        result = _run(["node", "--version"])
        actual_node = result.stdout.strip().removeprefix("v")
        if result.returncode == 0 and actual_node != expected_node:
            checks.append(
                Check(
                    "FAIL",
                    f"Node {actual_node} is active; repository requires {expected_node}",
                )
            )
        elif result.returncode == 0:
            checks.append(Check("PASS", f"Node version matches {expected_node}"))

    if shutil.which("pnpm") is not None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        package_manager = str(package.get("packageManager", ""))
        expected_pnpm = package_manager.removeprefix("pnpm@")
        result = _run(["pnpm", "--version"])
        actual_pnpm = result.stdout.strip()
        if result.returncode == 0 and actual_pnpm != expected_pnpm:
            checks.append(
                Check(
                    "FAIL",
                    f"pnpm {actual_pnpm} is active; repository requires {expected_pnpm}",
                )
            )
        elif result.returncode == 0:
            checks.append(Check("PASS", f"pnpm version matches {expected_pnpm}"))

    return checks


def _compose_check() -> Check:
    if shutil.which("docker") is None:
        return Check("FAIL", "cannot validate Compose because docker is unavailable")
    result = _run(["docker", "compose", "--env-file", ".env", "config", "--quiet"])
    if result.returncode != 0:
        return Check("FAIL", "docker compose configuration is invalid")
    return Check("PASS", "docker compose configuration is valid")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("base", "auth"),
        default="base",
        help="additional local subsystem configuration to validate",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    checks: list[Check] = []

    if not ENV_PATH.exists():
        checks.append(Check("FAIL", ".env does not exist; copy .env.example first"))
    else:
        env = parse_env_file(ENV_PATH)
        checks.extend(environment_checks(env, profile=str(args.profile)))

    checks.extend(_version_checks())
    if ENV_PATH.exists():
        checks.append(_compose_check())

    for check in checks:
        print(f"[{check.level}] {check.message}")

    failures = sum(check.level == "FAIL" for check in checks)
    warnings = sum(check.level == "WARN" for check in checks)
    if failures:
        print(f"doctor failed: {failures} failure(s), {warnings} warning(s)")
        return 1

    print(f"doctor passed: {warnings} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
