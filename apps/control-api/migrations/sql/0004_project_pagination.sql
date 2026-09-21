-- Support deterministic, Workspace-scoped Project cursor pagination.
CREATE INDEX idx_projects_workspace_created_id
    ON app.projects(workspace_id, created_at DESC, id DESC);
