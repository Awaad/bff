from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "infra" / "smoke.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("infra_smoke", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compose_file_is_repository_relative() -> None:
    module = _load_module()

    assert module.COMPOSE_FILE == module.ROOT / "compose.yaml"


def test_required_smoke_checks_are_registered() -> None:
    module = _load_module()

    assert set(module.CHECKS) == {
        "postgres",
        "rabbitmq",
        "valkey",
        "otel-collector",
    }


def test_wait_until_ready_reports_every_unhealthy_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "CHECKS",
        {
            "postgres": lambda: False,
            "rabbitmq": lambda: False,
        },
    )
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        module,
        "_compose",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {"stdout": "compose status", "stderr": ""},
        )(),
    )

    with pytest.raises(module.SmokeFailure) as exc_info:
        module.wait_until_ready(0)

    message = str(exc_info.value)
    assert "postgres" in message
    assert "rabbitmq" in message
    assert "compose status" in message
