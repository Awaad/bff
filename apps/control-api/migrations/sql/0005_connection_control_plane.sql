-- Support deterministic, Workspace-scoped Connection cursor pagination.
CREATE INDEX idx_connections_workspace_created_id
    ON app.connections(workspace_id, created_at DESC, id DESC);
