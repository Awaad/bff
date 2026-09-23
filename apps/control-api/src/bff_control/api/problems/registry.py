"""Canonical public API problem registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from bff_control.api.problems.schemas import ProblemCode


@dataclass(frozen=True, slots=True)
class ProblemSpec:
    """Static contract for one public problem type."""

    code: ProblemCode
    type_uri: str
    title: str
    status: int
    detail: str
    retryable: bool | None = None


PROBLEM_SPECS: Final[dict[ProblemCode, ProblemSpec]] = {
    ProblemCode.AUTH_INVALID_CREDENTIALS: ProblemSpec(
        code=ProblemCode.AUTH_INVALID_CREDENTIALS,
        type_uri="urn:uuid:60277549-1ffa-560c-b5f1-80b82f0ce19f",
        title="Invalid authentication credentials",
        status=401,
        detail="Authentication could not be completed.",
    ),
    ProblemCode.AUTH_EMAIL_VERIFICATION_REQUIRED: ProblemSpec(
        code=ProblemCode.AUTH_EMAIL_VERIFICATION_REQUIRED,
        type_uri="urn:uuid:d3468a7d-6ab3-5040-9f14-89c811f0b0a1",
        title="Email verification required",
        status=403,
        detail="Verify the authentication provider email before continuing.",
        retryable=False,
    ),
    ProblemCode.AUTH_ACCOUNT_LINK_REQUIRED: ProblemSpec(
        code=ProblemCode.AUTH_ACCOUNT_LINK_REQUIRED,
        type_uri="urn:uuid:a90a34d0-9660-51f4-9732-5f134b23b3a1",
        title="Account linking required",
        status=409,
        detail="An existing BFF account must be linked explicitly before continuing.",
        retryable=False,
    ),
    ProblemCode.AUTH_PROVIDER_UNAVAILABLE: ProblemSpec(
        code=ProblemCode.AUTH_PROVIDER_UNAVAILABLE,
        type_uri="urn:uuid:4b7e9b99-220d-5b6f-b051-56c00818c362",
        title="Authentication service unavailable",
        status=503,
        detail="Authentication is temporarily unavailable.",
        retryable=True,
    ),
    ProblemCode.WORKSPACE_NOT_FOUND: ProblemSpec(
        code=ProblemCode.WORKSPACE_NOT_FOUND,
        type_uri="urn:uuid:14e7c170-79a8-550d-a696-9cbe4d8a089f",
        title="Workspace not found",
        status=404,
        detail="The requested Workspace was not found.",
        retryable=False,
    ),
    ProblemCode.WORKSPACE_PERMISSION_DENIED: ProblemSpec(
        code=ProblemCode.WORKSPACE_PERMISSION_DENIED,
        type_uri="urn:uuid:9a590bea-29bf-571e-a9ac-802214c8d53e",
        title="Workspace permission denied",
        status=403,
        detail="The active Workspace role does not permit this operation.",
        retryable=False,
    ),
    ProblemCode.WORKSPACE_NOT_ACTIVE: ProblemSpec(
        code=ProblemCode.WORKSPACE_NOT_ACTIVE,
        type_uri="urn:uuid:dc40c9d8-61fc-5425-97bb-46ca0d799d69",
        title="Workspace is not active",
        status=409,
        detail="The Workspace lifecycle does not permit this operation.",
        retryable=False,
    ),
    ProblemCode.PROJECT_NOT_FOUND: ProblemSpec(
        code=ProblemCode.PROJECT_NOT_FOUND,
        type_uri="urn:uuid:11f1e95b-3a4c-512e-b2cf-a962f52b5db2",
        title="Project not found",
        status=404,
        detail="The requested Project was not found.",
        retryable=False,
    ),
    ProblemCode.REQUEST_VALIDATION_FAILED: ProblemSpec(
        code=ProblemCode.REQUEST_VALIDATION_FAILED,
        type_uri="urn:uuid:542c876a-0825-5cc6-a84b-f55bccc0087a",
        title="Request validation failed",
        status=422,
        detail="One or more request fields are invalid.",
        retryable=False,
    ),
    ProblemCode.REQUEST_NOT_FOUND: ProblemSpec(
        code=ProblemCode.REQUEST_NOT_FOUND,
        type_uri="urn:uuid:bc67b9ce-02f7-540e-b0c1-5015c66635e3",
        title="Not found",
        status=404,
        detail="The requested endpoint was not found.",
        retryable=False,
    ),
    ProblemCode.REQUEST_METHOD_NOT_ALLOWED: ProblemSpec(
        code=ProblemCode.REQUEST_METHOD_NOT_ALLOWED,
        type_uri="urn:uuid:0aeb43e6-7822-5a7c-bf4c-9e789b15bccd",
        title="Method not allowed",
        status=405,
        detail="The requested method is not supported for this endpoint.",
        retryable=False,
    ),
    ProblemCode.REQUEST_REJECTED: ProblemSpec(
        code=ProblemCode.REQUEST_REJECTED,
        type_uri="urn:uuid:d72f20c6-a0d5-5e45-8c3f-08b1150fec95",
        title="Request rejected",
        status=400,
        detail="The request could not be accepted.",
    ),
    ProblemCode.INTERNAL_ERROR: ProblemSpec(
        code=ProblemCode.INTERNAL_ERROR,
        type_uri="urn:uuid:c10c4a56-f258-50ec-a667-000c307d32b3",
        title="Internal server error",
        status=500,
        detail="The request could not be completed.",
    ),
}


def validate_problem_registry() -> None:
    """Fail fast if public problem identifiers are accidentally reused."""

    codes = {spec.code for spec in PROBLEM_SPECS.values()}
    type_uris = {spec.type_uri for spec in PROBLEM_SPECS.values()}
    if codes != set(PROBLEM_SPECS):
        raise RuntimeError("problem registry keys and codes must match")
    if len(type_uris) != len(PROBLEM_SPECS):
        raise RuntimeError("problem type identifiers must be unique")
