#!/usr/bin/env python3
"""Smoke-test the local stateful infrastructure.

This script never mutates application data. It verifies that the four local
dependencies are reachable and responding through their real service APIs.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "compose.yaml"


class SmokeFailure(RuntimeError):
    """Raised when an infrastructure dependency is not ready."""


def _run(
    args: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        check=check,
        capture_output=capture_output,
        text=True,
    )


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        check=check,
    )


def require_docker() -> None:
    if shutil.which("docker") is None:
        raise SmokeFailure("docker executable is not available")

    result = _run(["docker", "compose", "version"], check=False)
    if result.returncode != 0:
        raise SmokeFailure(
            "Docker Compose v2 is unavailable: "
            f"{(result.stderr or result.stdout).strip()}",
        )


def validate_compose() -> None:
    result = _compose("config", "--quiet", check=False)
    if result.returncode != 0:
        raise SmokeFailure(
            "docker compose config validation failed: "
            f"{(result.stderr or result.stdout).strip()}",
        )


def postgres_ready() -> bool:
    result = _compose(
        "exec",
        "-T",
        "postgres",
        "pg_isready",
        "-U",
        os.environ.get("POSTGRES_USER", "bff"),
        "-d",
        os.environ.get("POSTGRES_DB", "bff"),
        "-h",
        "127.0.0.1",
        check=False,
    )
    return result.returncode == 0


def rabbitmq_ready() -> bool:
    result = _compose(
        "exec",
        "-T",
        "rabbitmq",
        "rabbitmq-diagnostics",
        "-q",
        "ping",
        check=False,
    )
    return result.returncode == 0


def valkey_ready() -> bool:
    result = _compose(
        "exec",
        "-T",
        "valkey",
        "valkey-cli",
        "ping",
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "PONG"


def otel_ready() -> bool:
    port = os.environ.get("OTEL_HEALTH_PORT", "13133")
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/",
            timeout=2,
        ) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError):
        return False


CHECKS = {
    "postgres": postgres_ready,
    "rabbitmq": rabbitmq_ready,
    "valkey": valkey_ready,
    "otel-collector": otel_ready,
}


def wait_until_ready(timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    pending = set(CHECKS)

    while pending and time.monotonic() < deadline:
        for name in tuple(pending):
            try:
                if CHECKS[name]():
                    pending.remove(name)
                    print(f"[ready] {name}")
            except OSError:
                pass

        if pending:
            time.sleep(1)

    if pending:
        status = _compose("ps", check=False)
        details = status.stdout.strip() or status.stderr.strip()
        raise SmokeFailure(
            f"timed out waiting for: {', '.join(sorted(pending))}\n{details}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start",
        action="store_true",
        help="start the Compose stack before probing it",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="maximum readiness wait in seconds (default: 60)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        require_docker()
        validate_compose()

        if args.start:
            _compose("up", "-d")

        wait_until_ready(args.timeout)
    except SmokeFailure as error:
        print(f"infrastructure smoke test failed: {error}", file=sys.stderr)
        return 1

    print("local infrastructure smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
