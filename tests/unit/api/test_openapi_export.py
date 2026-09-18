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
        "/v1/workspaces",
        "/v1/workspaces/{workspace_id}",
    ]
    session = schema["paths"]["/v1/auth/session"]["post"]
    me = schema["paths"]["/v1/me"]["get"]
    assert session["operationId"] == "provisionSession"
    assert session["security"] == [{"HTTPBearer": []}]
    assert me["operationId"] == "getMe"
    assert me["security"] == [{"HTTPBearer": []}]

    workspaces = schema["paths"]["/v1/workspaces"]["get"]
    workspace = schema["paths"]["/v1/workspaces/{workspace_id}"]["get"]

    assert workspaces["operationId"] == "listWorkspaces"
    assert workspaces["security"] == [{"HTTPBearer": []}]

    assert workspace["operationId"] == "getWorkspace"
    assert workspace["security"] == [{"HTTPBearer": []}]
    for operation in (session, me, workspaces, workspace):
        assert "500" in operation["responses"]

        for response in operation["responses"].values():
            assert "X-Request-ID" in response["headers"]
    assert "application/problem+json" in session["responses"]["401"]["content"]
    assert "application/problem+json" in session["responses"]["500"]["content"]
    assert "application/problem+json" in me["responses"]["401"]["content"]

    assert "application/problem+json" in workspaces["responses"]["401"]["content"]
    assert "application/problem+json" in workspace["responses"]["401"]["content"]
    assert "application/problem+json" in workspace["responses"]["404"]["content"]

    assert "application/problem+json" in workspaces["responses"]["500"]["content"]
    assert "application/problem+json" in workspace["responses"]["500"]["content"]
