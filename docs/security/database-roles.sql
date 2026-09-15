-- Backend for Framer — database role hardening
-- Apply after schema creation using a migration/DBA role with CREATEROLE.
-- Application login roles should inherit one or more NOLOGIN group roles below.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_control_writer') THEN
        CREATE ROLE bff_control_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_runtime_writer') THEN
        CREATE ROLE bff_runtime_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_worker_writer') THEN
        CREATE ROLE bff_worker_writer NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA app TO bff_control_writer, bff_runtime_writer, bff_worker_writer;

-- Broad table access is intentionally illustrative and should be narrowed per service
-- as implementation entrypoints are created.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA app TO bff_control_writer;
GRANT SELECT, INSERT, UPDATE ON app.executions, app.execution_attempts, app.idempotency_records
    TO bff_runtime_writer;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA app TO bff_worker_writer;

-- Write-once immutable configuration/history.
REVOKE UPDATE, DELETE ON
    app.connection_revisions,
    app.credential_revisions,
    app.operation_versions,
    app.binding_revisions,
    app.sync_revisions,
    app.job_revisions,
    app.webhook_endpoint_revisions,
    app.usage_events,
    app.audit_events
FROM bff_control_writer, bff_runtime_writer, bff_worker_writer;

-- Attempts are not fully immutable: workers must complete lifecycle fields.
-- Identity/lineage fields remain non-updatable by granting only an explicit set.
REVOKE UPDATE ON app.execution_attempts FROM bff_runtime_writer, bff_worker_writer;
GRANT UPDATE (
    status,
    upstream_status,
    request_sent_at,
    response_received_at,
    duration_ms,
    request_bytes,
    response_bytes,
    error_category,
    error_code,
    retryable,
    trace_id,
    completed_at
) ON app.execution_attempts TO bff_runtime_writer, bff_worker_writer;

-- Outbox/queue and lifecycle tables remain mutable by the owning worker/domain.
-- Login-role membership and exact per-service table grants are deployment concerns.


-- CredentialSecretVersion material is immutable, but lifecycle transitions and secure
-- destruction legitimately mutate status/timestamps and clear encrypted material.
REVOKE UPDATE ON app.credential_secret_versions
    FROM bff_control_writer, bff_runtime_writer, bff_worker_writer;
GRANT UPDATE (
    status,
    activated_at,
    revoked_at,
    destroyed_at,
    ciphertext,
    wrapped_dek,
    kms_key_ref,
    nonce
) ON app.credential_secret_versions TO bff_control_writer, bff_worker_writer;

-- Domain code must permit ciphertext/wrapped-DEK clearing only as part of DESTROYED.
-- It may never replace one secret value with another inside the same SecretVersion.
