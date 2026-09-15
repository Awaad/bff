from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "db" / "verify_baseline_snapshot.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_baseline_snapshot", SCRIPT)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_migration_assets_match_accepted_specs() -> None:
    module = _load_script()

    assert module.verify() == []


def test_transaction_control_is_removed_from_migration_snapshot() -> None:
    module = _load_script()
    sql = module.MIGRATION_SCHEMA.read_text(encoding="utf-8")

    statements = {line.strip() for line in sql.splitlines()}

    assert "BEGIN;" not in statements
    assert "COMMIT;" not in statements
