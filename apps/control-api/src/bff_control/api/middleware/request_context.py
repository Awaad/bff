"""Request context, correlation headers, and safe access logging."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from opentelemetry import trace
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bff_control.api.context import (
    RequestContext,
    bind_request_context,
    reset_request_context,
)
from bff_control.core.ids import uuid7

_ACCESS_LOGGER = logging.getLogger("bff_control.api.access")


def _active_trace_id() -> str | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return f"{span_context.trace_id:032x}"


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return "<unmatched>"


class RequestContextMiddleware:
    """Attach canonical correlation state without owning domain behavior."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = uuid7()
        trace_id = _active_trace_id()
        context = RequestContext(
            request_id=request_id,
            trace_id=trace_id,
            started_at=datetime.now(tz=UTC),
        )
        scope.setdefault("state", {})["request_context"] = context

        current_span = trace.get_current_span()
        if current_span.get_span_context().is_valid:
            current_span.set_attribute("bff.request.id", str(request_id))

        token = bind_request_context(context)
        started_ns = time.perf_counter_ns()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                message["headers"] = [
                    (name, value)
                    for name, value in message["headers"]
                    if name.lower() != b"x-request-id"
                ]
                message["headers"].append((b"x-request-id", str(request_id).encode("ascii")))
            await send(message)

        try:
            await self._app(scope, receive, send_with_request_id)
        finally:
            duration_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
            _ACCESS_LOGGER.info(
                "http_request_completed",
                extra={
                    "request_id": str(request_id),
                    "trace_id": trace_id,
                    "method": scope.get("method", ""),
                    "route": _route_template(scope),
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            reset_request_context(token)
