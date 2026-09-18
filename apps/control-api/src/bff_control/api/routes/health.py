"""Process health endpoints."""

from __future__ import annotations

from typing import Literal, cast

from bff_control.api.contracts import DatabaseLifecycle, TelemetryLifecycle
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]


@router.get(
    "/livez",
    operation_id="livez",
    response_model=LivenessResponse,
    summary="Liveness probe",
)
async def livez() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get(
    "/readyz",
    operation_id="readyz",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "Database is not ready",
        },
    },
    summary="Readiness probe",
)
async def readyz(request: Request, response: Response) -> ReadinessResponse:
    database = cast(DatabaseLifecycle, request.app.state.database)
    telemetry = cast(TelemetryLifecycle, request.app.state.telemetry)
    with telemetry.tracer.start_as_current_span("health.readiness") as span:
        ready = await database.is_ready()
        span.set_attribute("bff.database.ready", ready)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready")
    return ReadinessResponse(status="ready")
