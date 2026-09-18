"""RFC 9457 public problem representation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ProblemCode(StrEnum):
    """Stable machine-readable public problem codes."""

    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_EMAIL_VERIFICATION_REQUIRED = "AUTH_EMAIL_VERIFICATION_REQUIRED"
    AUTH_ACCOUNT_LINK_REQUIRED = "AUTH_ACCOUNT_LINK_REQUIRED"
    AUTH_PROVIDER_UNAVAILABLE = "AUTH_PROVIDER_UNAVAILABLE"
    REQUEST_VALIDATION_FAILED = "REQUEST_VALIDATION_FAILED"
    REQUEST_NOT_FOUND = "REQUEST_NOT_FOUND"
    REQUEST_METHOD_NOT_ALLOWED = "REQUEST_METHOD_NOT_ALLOWED"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ValidationIssueCode(StrEnum):
    """Stable machine-readable validation issue codes."""

    REQUIRED = "REQUIRED"
    INVALID_JSON = "INVALID_JSON"
    INVALID_VALUE = "INVALID_VALUE"


class ValidationIssue(BaseModel):
    """One safe request-validation issue."""

    pointer: str
    code: ValidationIssueCode
    detail: str


class ProblemDetail(BaseModel):
    """RFC 9457 problem plus stable BFF extensions."""

    type: str
    title: str
    status: int = Field(ge=100, le=599)
    detail: str
    instance: str
    code: ProblemCode
    request_id: str
    retryable: bool | None = None
    errors: list[ValidationIssue] | None = None
