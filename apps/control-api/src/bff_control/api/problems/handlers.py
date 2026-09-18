"""Central exception-to-Problem-Details mapping."""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from bff_control.api.context import require_request_context
from bff_control.api.problems.exceptions import ProblemException
from bff_control.api.problems.registry import PROBLEM_SPECS
from bff_control.api.problems.schemas import (
    ProblemCode,
    ProblemDetail,
    ValidationIssue,
    ValidationIssueCode,
)
from bff_control.domains.authentication.contracts import PrincipalAuthenticationError
from bff_control.domains.authentication.provisioning_contracts import (
    AccountLinkRequiredError,
    EmailVerificationRequiredError,
    ExternalUserProfileUnavailableError,
    SessionProvisioningAuthenticationError,
)

_PROBLEM_LOGGER = logging.getLogger("bff_control.api.problems")


def _safe_framework_headers(exc: Exception) -> dict[str, str]:
    raw_headers = getattr(exc, "headers", None)
    if not isinstance(raw_headers, dict):
        return {}
    allowed = {"allow", "retry-after", "www-authenticate"}
    return {
        str(name): str(value)
        for name, value in raw_headers.items()
        if str(name).casefold() in allowed
    }


def _problem_response(
    request: Request,
    code: ProblemCode,
    *,
    errors: list[ValidationIssue] | None = None,
    headers: dict[str, str] | None = None,
    status_override: int | None = None,
    title_override: str | None = None,
) -> JSONResponse:
    context = require_request_context(request)
    spec = PROBLEM_SPECS[code]
    status_code = status_override or spec.status
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = str(context.request_id)

    problem = ProblemDetail(
        type=spec.type_uri,
        title=title_override or spec.title,
        status=status_code,
        detail=spec.detail,
        instance=f"urn:uuid:{context.request_id}",
        code=code,
        request_id=str(context.request_id),
        retryable=spec.retryable,
        errors=errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        headers=response_headers,
        media_type="application/problem+json",
    )


def _validation_pointer(location: tuple[str | int, ...]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in location]
    return "#/" + "/".join(escaped)


def _validation_issue_code(error_type: str) -> ValidationIssueCode:
    if error_type == "missing":
        return ValidationIssueCode.REQUIRED
    if error_type == "json_invalid":
        return ValidationIssueCode.INVALID_JSON
    return ValidationIssueCode.INVALID_VALUE


def _validation_issue_detail(code: ValidationIssueCode) -> str:
    if code is ValidationIssueCode.REQUIRED:
        return "Field is required."
    if code is ValidationIssueCode.INVALID_JSON:
        return "Request body is not valid JSON."
    return "Value is invalid."


async def _problem_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, ProblemException):
        raise TypeError("problem exception handler received unexpected exception")
    return _problem_response(request, exc.code, headers=exc.headers)


async def _invalid_authentication_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del exc
    return _problem_response(
        request,
        ProblemCode.AUTH_INVALID_CREDENTIALS,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _email_verification_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del exc
    return _problem_response(
        request,
        ProblemCode.AUTH_EMAIL_VERIFICATION_REQUIRED,
    )


async def _account_link_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del exc
    return _problem_response(request, ProblemCode.AUTH_ACCOUNT_LINK_REQUIRED)


async def _provider_unavailable_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del exc
    return _problem_response(request, ProblemCode.AUTH_PROVIDER_UNAVAILABLE)


async def _validation_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise TypeError("validation handler received unexpected exception")

    issues: list[ValidationIssue] = []
    for error in exc.errors():
        location = error.get("loc")
        if not isinstance(location, tuple):
            location = tuple(location or ())
        typed_location = tuple(part for part in location if isinstance(part, (str, int)))
        issue_code = _validation_issue_code(str(error.get("type", "")))
        issues.append(
            ValidationIssue(
                pointer=_validation_pointer(typed_location),
                code=issue_code,
                detail=_validation_issue_detail(issue_code),
            )
        )

    return _problem_response(
        request,
        ProblemCode.REQUEST_VALIDATION_FAILED,
        errors=issues,
    )


async def _not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return _problem_response(
        request,
        ProblemCode.REQUEST_NOT_FOUND,
        headers=_safe_framework_headers(exc),
    )


async def _method_not_allowed_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    return _problem_response(
        request,
        ProblemCode.REQUEST_METHOD_NOT_ALLOWED,
        headers=_safe_framework_headers(exc),
    )


async def _http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise TypeError("HTTP exception handler received unexpected exception")
    try:
        title = HTTPStatus(exc.status_code).phrase
    except ValueError:
        title = PROBLEM_SPECS[ProblemCode.REQUEST_REJECTED].title
    return _problem_response(
        request,
        ProblemCode.REQUEST_REJECTED,
        headers=_safe_framework_headers(exc),
        status_override=exc.status_code,
        title_override=title,
    )


async def _internal_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    context = require_request_context(request)
    _PROBLEM_LOGGER.error(
        "unhandled_api_exception",
        extra={
            "request_id": str(context.request_id),
            "trace_id": context.trace_id,
            "exception_type": type(exc).__name__,
        },
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _problem_response(request, ProblemCode.INTERNAL_ERROR)


def register_problem_handlers(app: FastAPI) -> None:
    """Install the central public problem-mapping layer."""

    app.add_exception_handler(ProblemException, _problem_exception_handler)
    app.add_exception_handler(
        PrincipalAuthenticationError,
        _invalid_authentication_handler,
    )
    app.add_exception_handler(
        SessionProvisioningAuthenticationError,
        _invalid_authentication_handler,
    )
    app.add_exception_handler(
        EmailVerificationRequiredError,
        _email_verification_handler,
    )
    app.add_exception_handler(AccountLinkRequiredError, _account_link_handler)
    app.add_exception_handler(
        ExternalUserProfileUnavailableError,
        _provider_unavailable_handler,
    )
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(404, _not_found_handler)
    app.add_exception_handler(405, _method_not_allowed_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _internal_error_handler)
