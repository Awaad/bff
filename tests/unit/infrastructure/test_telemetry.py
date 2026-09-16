from __future__ import annotations

from bff_control.core.settings import ApplicationSettings
from bff_control.infrastructure.observability.telemetry import configure_telemetry


def test_disabled_telemetry_has_no_external_exporter() -> None:
    settings = ApplicationSettings(
        _env_file=None,
        telemetry_enabled=False,
    )

    telemetry = configure_telemetry(settings)
    try:
        span = telemetry.tracer.start_span("test")
        assert not span.is_recording()
        span.end()
    finally:
        telemetry.shutdown()
