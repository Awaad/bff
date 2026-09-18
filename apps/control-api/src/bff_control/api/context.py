"""Request-level transport correlation context."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import Request


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Server-generated correlation state for one HTTP request."""

    request_id: UUID
    trace_id: str | None
    started_at: datetime


_current_request_context: ContextVar[RequestContext | None] = ContextVar(
    "bff_request_context",
    default=None,
)


def bind_request_context(context: RequestContext) -> Token[RequestContext | None]:
    return _current_request_context.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _current_request_context.reset(token)


def current_request_context() -> RequestContext | None:
    return _current_request_context.get()


def require_request_context(request: Request) -> RequestContext:
    context = getattr(request.state, "request_context", None)
    if not isinstance(context, RequestContext):
        raise RuntimeError("request context middleware is not installed")
    return context
