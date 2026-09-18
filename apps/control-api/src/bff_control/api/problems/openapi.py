"""OpenAPI support for the public Problem Details contract."""

from __future__ import annotations

from typing import Any, Final

from fastapi import FastAPI

from bff_control.api.problems.registry import PROBLEM_SPECS
from bff_control.api.problems.schemas import ProblemCode, ProblemDetail

_PROBLEM_SCHEMA_REF: Final = "#/components/schemas/ProblemDetail"
_REQUEST_ID_HEADER: Final[dict[str, Any]] = {
    "description": "Server-generated request correlation identifier.",
    "schema": {"type": "string", "format": "uuid"},
}
_HTTP_METHODS: Final = {
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
}


def problem_openapi_response(code: ProblemCode) -> dict[str, Any]:
    spec = PROBLEM_SPECS[code]
    return {"model": ProblemDetail, "description": spec.title}


def _problem_response_document(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/problem+json": {
                "schema": {"$ref": _PROBLEM_SCHEMA_REF},
            }
        },
    }


def _is_problem_schema(content_entry: object) -> bool:
    if not isinstance(content_entry, dict):
        return False
    schema = content_entry.get("schema")
    return isinstance(schema, dict) and schema.get("$ref") == _PROBLEM_SCHEMA_REF


def _normalize_problem_media_type(response: dict[str, Any]) -> None:
    content = response.get("content")
    if not isinstance(content, dict):
        return
    application_json = content.get("application/json")
    if not _is_problem_schema(application_json):
        return
    content["application/problem+json"] = application_json
    del content["application/json"]


def _replace_validation_response(operation: dict[str, Any]) -> None:
    responses = operation.get("responses")
    if isinstance(responses, dict) and "422" in responses:
        responses["422"] = _problem_response_document("Request validation failed")


def _inject_internal_error(path: str, operation: dict[str, Any]) -> None:
    if not path.startswith("/v1/"):
        return
    responses = operation.setdefault("responses", {})
    if isinstance(responses, dict):
        responses.setdefault(
            "500",
            _problem_response_document("Internal server error"),
        )


def _inject_request_id_header(response: dict[str, Any]) -> None:
    headers = response.setdefault("headers", {})
    if isinstance(headers, dict):
        headers.setdefault("X-Request-ID", _REQUEST_ID_HEADER)


def _normalize_operation(path: str, operation: dict[str, Any]) -> None:
    _replace_validation_response(operation)
    _inject_internal_error(path, operation)
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return
    for response in responses.values():
        if isinstance(response, dict):
            _normalize_problem_media_type(response)
            _inject_request_id_header(response)


def normalize_openapi_contract(schema: dict[str, Any]) -> dict[str, Any]:
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        return schema
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method in _HTTP_METHODS and isinstance(operation, dict):
                _normalize_operation(path, operation)
    return schema


class ControlApi(FastAPI):
    """FastAPI subclass with deterministic BFF contract normalization."""

    def openapi(self) -> dict[str, Any]:
        if self.openapi_schema is not None:
            return self.openapi_schema
        schema = normalize_openapi_contract(super().openapi())
        self.openapi_schema = schema
        return schema
