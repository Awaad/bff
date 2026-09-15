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
CONTROL_PACKAGE: Final = "bff_control"
FORBIDDEN_CORE_TARGETS: Final = frozenset({"api", "domains", "infrastructure"})
FORBIDDEN_DOMAIN_TARGETS: Final = frozenset({"api"})
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


def _source_module_parts(path: Path) -> tuple[str, ...] | None:
    """Return the dotted module path for files inside the control package."""

    parts = path.parts
    try:
        marker = parts.index(CONTROL_PACKAGE)
    except ValueError:
        return None

    module_parts = list(parts[marker:])
    if not module_parts or path.suffix != ".py":
        return None

    if path.name == "__init__.py":
        module_parts.pop()
    else:
        module_parts[-1] = path.stem

    return tuple(module_parts)


def _resolve_import_from(
    path: Path,
    node: ast.ImportFrom,
) -> tuple[str, ...] | None:
    module_tail = tuple(node.module.split(".")) if node.module else ()

    if node.level == 0:
        return module_tail

    source_module = _source_module_parts(path)
    if source_module is None:
        return None

    package_parts = source_module if path.name == "__init__.py" else source_module[:-1]
    parents_to_remove = node.level - 1
    if parents_to_remove > len(package_parts):
        return None

    base = package_parts[: len(package_parts) - parents_to_remove]
    return (*base, *module_tail)


def _import_targets(
    path: Path,
    node: ast.Import | ast.ImportFrom,
) -> tuple[tuple[str, ...], ...]:
    if isinstance(node, ast.Import):
        return tuple(tuple(alias.name.split(".")) for alias in node.names)

    base = _resolve_import_from(path, node)
    if not base:
        return ()

    targets: set[tuple[str, ...]] = {base}
    for alias in node.names:
        if alias.name == "*":
            continue
        targets.add((*base, *alias.name.split(".")))

    return tuple(sorted(targets))


def _control_context(path: Path) -> tuple[str | None, str | None]:
    module_parts = _source_module_parts(path)
    if module_parts is None or len(module_parts) < 2:
        return None, None

    layer = module_parts[1]
    domain = module_parts[2] if layer == "domains" and len(module_parts) >= 3 else None
    return layer, domain


def _target_context(parts: tuple[str, ...]) -> tuple[str | None, str | None]:
    if not parts or parts[0] != CONTROL_PACKAGE or len(parts) < 2:
        return None, None

    layer = parts[1]
    domain = parts[2] if layer == "domains" and len(parts) >= 3 else None
    return layer, domain


def _check_import(path: Path, node: ast.Import | ast.ImportFrom) -> list[Violation]:
    source_layer, source_domain = _control_context(path)
    violations: list[Violation] = []

    for parts in _import_targets(path, node):
        target_layer, target_domain = _target_context(parts)
        if target_layer is None:
            continue

        rendered_target = ".".join(parts)

        if source_layer == "core" and target_layer in FORBIDDEN_CORE_TARGETS:
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    f"core modules must not import {target_layer}: {rendered_target}",
                )
            )
            continue

        if source_layer == "domains" and target_layer in FORBIDDEN_DOMAIN_TARGETS:
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    f"domain modules must not import {target_layer}: {rendered_target}",
                )
            )
            continue

        if (
            source_layer != "domains"
            or source_domain is None
            or target_layer != "domains"
            or target_domain is None
            or target_domain == source_domain
        ):
            continue

        imported_tail = set(parts[3:])
        forbidden = imported_tail & FORBIDDEN_CROSS_DOMAIN_MODULES
        if forbidden:
            forbidden_name = sorted(forbidden)[0]
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    "cross-domain imports may not reach another domain's "
                    f"{forbidden_name} module: {rendered_target}",
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
