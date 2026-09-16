-- Backend for Framer — current database application-role policy
-- Current through migration 0002_user_auth_identities.
-- Run as the same schema/migration owner that creates future objects.

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
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_retention') THEN
        CREATE ROLE bff_retention NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA app
TO bff_control_writer, bff_runtime_writer, bff_worker_writer, bff_retention;

-- Control plane.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA app TO bff_control_writer;

-- Binding kind/exposure are stable identity attributes.
REVOKE UPDATE ON app.bindings FROM bff_control_writer;
GRANT UPDATE (
    name,
    status,
    active_revision_id,
    updated_at,
    archived_at
) ON app.bindings TO bff_control_writer;

-- External authentication subject identity is stable security state.
REVOKE UPDATE ON app.user_auth_identities FROM bff_control_writer;
GRANT UPDATE (
    status,
    updated_at,
    disabled_at
) ON app.user_auth_identities TO bff_control_writer;

-- Runtime admission/config reads.
GRANT SELECT ON
    app.workspaces,
    app.projects,
    app.binding_public_identifiers,
    app.bindings,
    app.binding_revisions,
    app.connections,
    app.connection_revisions,
    app.connection_project_access,
    app.credentials,
    app.credential_revisions,
    app.credential_secret_versions,
    app.operations,
    app.operation_versions,
    app.entitlement_grants,
    app.project_profile_assignments,
    app.usage_buckets
TO bff_runtime_writer;

-- Runtime durable writes.
GRANT SELECT, INSERT, UPDATE ON
    app.executions,
    app.execution_attempts,
    app.idempotency_records
TO bff_runtime_writer;

GRANT SELECT, INSERT ON
    app.usage_events,
    app.outbox_events
TO bff_runtime_writer;

-- Initial async worker deployment is broad; split by worker service later.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA app TO bff_worker_writer;

-- Workers execute asynchronous work; they do not author or publish Bindings.
-- This revoke must remain after the blanket worker grant so UPDATE is not
-- accidentally reintroduced by statement ordering.
REVOKE UPDATE ON app.bindings FROM bff_worker_writer;

-- Authentication identities are control-plane security state.
REVOKE ALL PRIVILEGES ON app.user_auth_identities
FROM bff_runtime_writer, bff_worker_writer, bff_retention;

-- Write-once published/history state.
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

-- Attempt identity is immutable, lifecycle/result fields are mutable.
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

-- SecretVersion material is immutable as a version; lifecycle/destruction may clear it.
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
) ON app.credential_secret_versions
TO bff_control_writer, bff_worker_writer;

-- Retention is a separate operational privilege.
GRANT SELECT, DELETE ON
    app.idempotency_records,
    app.consumer_deduplication,
    app.outbox_events,
    app.notification_delivery_attempts,
    app.notification_deliveries,
    app.notifications
TO bff_retention;

GRANT SELECT ON app.webhook_deliveries TO bff_retention;
GRANT UPDATE (payload_ref, payload_purged_at)
ON app.webhook_deliveries TO bff_retention;

-- Future objects. These defaults apply only to objects created by the role that
-- executes this statement. Migrations must run under that owner or specify FOR ROLE.
ALTER DEFAULT PRIVILEGES IN SCHEMA app
    GRANT SELECT ON TABLES TO bff_control_writer, bff_worker_writer;

-- Runtime and retention intentionally receive no blanket future-table rights.
-- Every migration extending those surfaces must grant privileges explicitly.
