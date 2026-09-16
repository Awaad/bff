"""OpenTelemetry bootstrap for the control API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer

from bff_control.core.settings import ApplicationSettings


@dataclass(frozen=True)
class Telemetry:
    """Own the tracer and exporter shutdown lifecycle."""

    tracer: Tracer
    _shutdown: Callable[[], None]

    @classmethod
    def disabled(cls) -> Telemetry:
        provider = trace.NoOpTracerProvider()
        return cls(
            tracer=provider.get_tracer("bff_control"),
            _shutdown=lambda: None,
        )

    def shutdown(self) -> None:
        self._shutdown()


def configure_telemetry(settings: ApplicationSettings) -> Telemetry:
    """Configure OTLP/HTTP tracing without mutating OpenTelemetry global state."""

    if not settings.telemetry_enabled:
        return Telemetry.disabled()

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "deployment.environment.name": settings.environment,
        },
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=str(settings.otel_traces_endpoint))
    provider.add_span_processor(BatchSpanProcessor(exporter))

    return Telemetry(
        tracer=provider.get_tracer("bff_control"),
        _shutdown=provider.shutdown,
    )
