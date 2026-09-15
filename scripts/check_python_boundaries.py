#!/usr/bin/env python3
"""Enforce Python import boundaries for the modular control-plane codebase."""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PYTHON_SOURCE_ROOT_NAMES: Final = frozenset({"apps", "packages", "workers"})
FORBIDDEN_CROSS_DOMAIN_MODULES: Final = frozenset({"models", "repository"})


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    message: str

    def render(self, root: Path) -> str:
        try:
            display_path = self.path.relative_to(root)
        except ValueError:
            display_path = self.path
        return f"{display_path}:{self.line}: {self.message}"


def _module_parts(node: ast.Import | ast.ImportFrom) -> tuple[tuple[str, ...], ...]:
    if isinstance(node, ast.Import):
        return tuple(tuple(alias.name.split(".")) for alias in node.names)
    if node.level != 0 or node.module is None:
        return ()
    return (tuple(node.module.split(".")),)


def _domain_context(path: Path) -> tuple[str, int] | None:
    parts = path.parts
    try:
        marker = parts.index("domains")
    except ValueError:
        return None
    if marker + 1 >= len(parts):
        return None
    return parts[marker + 1], marker


def _is_core_file(path: Path) -> bool:
    return "core" in path.parts


def _check_import(path: Path, node: ast.Import | ast.ImportFrom) -> list[Violation]:
    violations: list[Violation] = []
    domain_context = _domain_context(path)

    for parts in _module_parts(node):
        if _is_core_file(path) and "domains" in parts:
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    f"core modules must not import business domains: {'.'.join(parts)}",
                )
            )

        if domain_context is None or "domains" not in parts:
            continue

        current_domain, _ = domain_context
        domain_marker = parts.index("domains")
        if domain_marker + 1 >= len(parts):
            continue

        imported_domain = parts[domain_marker + 1]
        if imported_domain == current_domain:
            continue

        imported_tail = set(parts[domain_marker + 2 :])
        forbidden = imported_tail & FORBIDDEN_CROSS_DOMAIN_MODULES
        if forbidden:
            forbidden_name = sorted(forbidden)[0]
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    "cross-domain imports may not reach another domain's "
                    f"{forbidden_name} module: {'.'.join(parts)}",
                )
            )

    return violations


def check_file(path: Path) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        line = getattr(exc, "lineno", None) or 1
        return [Violation(path, line, f"unable to parse Python source: {exc}")]

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.extend(_check_import(path, node))
    return violations


def discover_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for source_root_name in PYTHON_SOURCE_ROOT_NAMES:
        source_root = root / source_root_name
        if not source_root.exists():
            continue
        files.extend(
            path
            for path in source_root.rglob("*.py")
            if ".venv" not in path.parts and "node_modules" not in path.parts
        )
    return sorted(files)


def check_repository(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in discover_python_files(root):
        violations.extend(check_file(path))
    return violations


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the script's parent repository)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()
    violations = check_repository(root)
    if not violations:
        return 0

    for violation in violations:
        print(violation.render(root), file=sys.stderr)
    print(f"architecture boundary check failed: {len(violations)} violation(s)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
