from __future__ import annotations

import json

from scripts.api.export_openapi import render_openapi


def test_openapi_render_is_deterministic() -> None:
    first = render_openapi()
    second = render_openapi()

    assert first == second
    assert first.endswith("\n")

    schema = json.loads(first)
    assert schema["info"] == {
        "title": "Backend for Framer Control API",
        "version": "0.0.0",
    }
    assert sorted(schema["paths"]) == [
        "/livez",
        "/readyz",
        "/v1/auth/session",
        "/v1/me",
    ]
    assert schema["paths"]["/v1/auth/session"]["post"]["operationId"] == ("provisionSession")
    assert schema["paths"]["/v1/auth/session"]["post"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"]["/v1/me"]["get"]["operationId"] == "getMe"
    assert schema["paths"]["/v1/me"]["get"]["security"] == [{"HTTPBearer": []}]
