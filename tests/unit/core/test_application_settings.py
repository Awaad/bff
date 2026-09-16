from __future__ import annotations

import pytest
from bff_control.core.settings import ApplicationSettings


def test_application_settings_have_safe_process_defaults() -> None:
    settings = ApplicationSettings(_env_file=None)

    assert settings.service_name == "bff-control"
    assert settings.environment == "dev"
    assert settings.telemetry_enabled is False
    assert str(settings.otel_traces_endpoint) == "http://127.0.0.1:4318/v1/traces"


def test_application_settings_load_bff_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BFF_SERVICE_NAME", "control-test")
    monkeypatch.setenv("BFF_ENVIRONMENT", "test")
    monkeypatch.setenv("BFF_TELEMETRY_ENABLED", "true")
    monkeypatch.setenv(
        "BFF_OTEL_TRACES_ENDPOINT",
        "http://collector:4318/v1/traces",
    )

    settings = ApplicationSettings(_env_file=None)

    assert settings.service_name == "control-test"
    assert settings.environment == "test"
    assert settings.telemetry_enabled is True
    assert str(settings.otel_traces_endpoint) == "http://collector:4318/v1/traces"
