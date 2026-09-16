#!/usr/bin/env python3
"""Render or verify the canonical control API OpenAPI document."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bff_control.bootstrap import create_application

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "artifacts" / "openapi" / "control-api.json"


def render_openapi() -> str:
    """Render deterministic OpenAPI JSON without starting application lifespan."""

    schema = create_application().openapi()
    return (
        json.dumps(
            schema,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_openapi(output: Path) -> None:
    """Write OpenAPI atomically."""

    rendered = render_openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(output)


def check_openapi(output: Path) -> bool:
    """Return whether the committed OpenAPI document matches current code."""

    if not output.exists():
        return False
    return output.read_text(encoding="utf-8") == render_openapi()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.check:
        if not check_openapi(args.output):
            print(f"OpenAPI drift detected: {args.output}")
            return 1
        print(f"OpenAPI is current: {args.output}")
        return 0

    write_openapi(args.output)
    print(f"OpenAPI written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
