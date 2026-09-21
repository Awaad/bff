-- Backend for Framer
-- Canonical PostgreSQL desired schema
-- Baseline: V2.1 frozen 2026-09-13
-- Current through: 0004_project_pagination, 2026-09-21
-- Supersedes: Baseline V1 integrity review
--
-- IDs are application-generated UUIDv7. No database UUIDv7 function is assumed.
-- Lifecycle/status columns use TEXT + CHECK intentionally for rolling migration flexibility.
-- JSONB configuration is always schema-validated by its owning domain before persistence/publication.

BEGIN;

CREATE SCHEMA IF NOT EXISTS app;
SET search_path = app, public;

-- -----------------------------------------------------------------------------
-- Identity / Workspace
-- -----------------------------------------------------------------------------

CREATE TABLE users (
    id uuid PRIMARY KEY,
    email text NOT NULL,
    email_normalized text NOT NULL,
    display_name text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (email_normalized)
);

CREATE TABLE user_auth_identities (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    issuer text NOT NULL CHECK (length(issuer) > 0),
    subject text NOT NULL CHECK (length(subject) > 0),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz,
    CHECK (
        (status = 'ACTIVE' AND disabled_at IS NULL)
        OR (status = 'DISABLED' AND disabled_at IS NOT NULL)
    ),
    UNIQUE (issuer, subject)
);

CREATE INDEX ix_user_auth_identities_user_id
    ON user_auth_identities(user_id);

CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY,
    user_auth_identity_id uuid NOT NULL
        REFERENCES user_auth_identities(id) ON DELETE RESTRICT,
    provider_session_id text NOT NULL CHECK (length(provider_session_id) > 0),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revocation_reason text,
    provider_revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at),
    CHECK (
        (revoked_at IS NULL AND revocation_reason IS NULL)
        OR (
            revoked_at IS NOT NULL
            AND revocation_reason IS NOT NULL
            AND length(revocation_reason) > 0
        )
    ),
    CHECK (provider_revoked_at IS NULL OR revoked_at IS NOT NULL),
    UNIQUE (user_auth_identity_id, provider_session_id)
);

CREATE INDEX ix_auth_sessions_identity_active
    ON auth_sessions(user_auth_identity_id)
    WHERE revoked_at IS NULL;

CREATE INDEX ix_auth_sessions_active_expiry
    ON auth_sessions(expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE workspaces (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','ARCHIVED','PENDING_DELETION')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    UNIQUE (id)
);

CREATE TABLE workspace_memberships (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    role text NOT NULL CHECK (role IN ('OWNER','ADMIN','BUILDER','VIEWER')),
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ended_at IS NULL OR ended_at >= started_at),
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_workspace_memberships_active
    ON workspace_memberships(workspace_id, user_id)
    WHERE ended_at IS NULL;

CREATE TABLE workspace_invitations (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    email_normalized text NOT NULL,
    intended_role text NOT NULL CHECK (intended_role IN ('OWNER','ADMIN','BUILDER','VIEWER')),
    invited_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    token_hash bytea NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACCEPTED','REVOKED','EXPIRED')),
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (token_hash),
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_workspace_invitations_pending_email
    ON workspace_invitations(workspace_id, email_normalized)
    WHERE status = 'PENDING';

-- -----------------------------------------------------------------------------
-- Projects / Framer linkage
-- -----------------------------------------------------------------------------

CREATE TABLE projects (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','ARCHIVED','PENDING_DELETION')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    UNIQUE (workspace_id, id)
);

CREATE TABLE framer_authorizations (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','REAUTH_REQUIRED','REVOKED')),
    provider_account_id text,
    encrypted_state bytea,
    kms_key_ref text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id)
);

CREATE TABLE framer_project_links (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    framer_authorization_id uuid NOT NULL,
    framer_project_id text NOT NULL,
    status text NOT NULL DEFAULT 'PENDING_VERIFICATION'
        CHECK (status IN ('PENDING_VERIFICATION','ACTIVE','DISCONNECTED','VERIFICATION_FAILED')),
    ownership_verified_at timestamptz,
    ownership_verification_method text,
    ownership_verification_subject text,
    linked_at timestamptz,
    disconnected_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, framer_authorization_id) REFERENCES framer_authorizations(workspace_id, id) ON DELETE RESTRICT,
    CHECK (
        status <> 'ACTIVE'
        OR (
            ownership_verified_at IS NOT NULL
            AND ownership_verification_method IS NOT NULL
        )
    ),
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_framer_project_links_active_project
    ON framer_project_links(project_id) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX uq_framer_project_links_active_external
    ON framer_project_links(framer_project_id) WHERE status = 'ACTIVE';

CREATE TABLE project_domains (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    hostname text NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','VERIFIED','REVOKED')),
    verified_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE CASCADE,
    UNIQUE (project_id, hostname),
    UNIQUE (workspace_id, id)
);

-- -----------------------------------------------------------------------------
-- Billing / Entitlements / Usage
-- -----------------------------------------------------------------------------

CREATE TABLE billing_accounts (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL UNIQUE REFERENCES workspaces(id) ON DELETE RESTRICT,
    provider_key text NOT NULL,
    provider_customer_id text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider_key, provider_customer_id),
    UNIQUE (workspace_id, id)
);

CREATE TABLE subscriptions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    billing_account_id uuid NOT NULL,
    provider_subscription_id text,
    status text NOT NULL CHECK (status IN ('TRIALING','ACTIVE','PAST_DUE','PAUSED','CANCELLED','ENDED')),
    current_period_start timestamptz,
    current_period_end timestamptz,
    cancel_at_period_end boolean NOT NULL DEFAULT false,
    is_primary boolean NOT NULL DEFAULT true,
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    FOREIGN KEY (workspace_id, billing_account_id) REFERENCES billing_accounts(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, id),
    UNIQUE (provider_subscription_id)
);
CREATE UNIQUE INDEX uq_subscriptions_primary_active
    ON subscriptions(workspace_id)
    WHERE is_primary AND status IN ('TRIALING','ACTIVE','PAST_DUE','PAUSED');

CREATE TABLE subscription_items (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    subscription_id uuid NOT NULL,
    provider_item_id text,
    product_key text NOT NULL,
    quantity numeric(20,6) NOT NULL DEFAULT 1,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, subscription_id) REFERENCES subscriptions(workspace_id, id) ON DELETE CASCADE,
    UNIQUE (workspace_id, id),
    UNIQUE (provider_item_id)
);

CREATE TABLE entitlement_grants (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id uuid,
    entitlement_key text NOT NULL,
    value_json jsonb NOT NULL,
    source text NOT NULL CHECK (source IN ('SUBSCRIPTION','ADDON','FOUNDING_ACCESS','PROMOTION','MANUAL','ENTERPRISE_CONTRACT')),
    source_ref text,
    starts_at timestamptz NOT NULL DEFAULT now(),
    ends_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    CHECK (project_id IS NULL OR workspace_id IS NOT NULL),
    CHECK (ends_at IS NULL OR ends_at > starts_at),
    UNIQUE (workspace_id, id)
);

CREATE TABLE project_profile_assignments (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    profile_key text NOT NULL,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_project_profile_assignments_active
    ON project_profile_assignments(project_id)
    WHERE released_at IS NULL;

CREATE TABLE usage_events (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id uuid,
    metric_key text NOT NULL,
    quantity numeric(30,6) NOT NULL,
    source_type text NOT NULL,
    source_id uuid,
    dedupe_key text NOT NULL,
    occurred_at timestamptz NOT NULL,
    correction_of_event_id uuid REFERENCES usage_events(id) ON DELETE RESTRICT,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, metric_key, dedupe_key),
    UNIQUE (workspace_id, id)
);

CREATE TABLE usage_buckets (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id uuid,
    metric_key text NOT NULL,
    bucket_start timestamptz NOT NULL,
    bucket_end timestamptz NOT NULL,
    quantity numeric(30,6) NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, id),
    CHECK (bucket_end > bucket_start)
);
CREATE UNIQUE INDEX uq_usage_buckets_workspace_scope
    ON usage_buckets(workspace_id, metric_key, bucket_start)
    WHERE project_id IS NULL;
CREATE UNIQUE INDEX uq_usage_buckets_project_scope
    ON usage_buckets(workspace_id, project_id, metric_key, bucket_start)
    WHERE project_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- Connections / Credentials / Operations
-- -----------------------------------------------------------------------------

CREATE TABLE connections (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    name text NOT NULL,
    provider_key text NOT NULL,
    access_mode text NOT NULL DEFAULT 'WORKSPACE' CHECK (access_mode IN ('WORKSPACE','SELECTED_PROJECTS')),
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','DISABLED','ARCHIVED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    UNIQUE (workspace_id, id)
);


CREATE TABLE connection_drafts (
    connection_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    draft_json jsonb NOT NULL,
    updated_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, connection_id)
        REFERENCES connections(workspace_id, id) ON DELETE CASCADE
);

CREATE TABLE connection_revisions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    revision_number bigint NOT NULL CHECK (revision_number > 0),
    definition_schema_version integer NOT NULL CHECK (definition_schema_version > 0),
    config_json jsonb NOT NULL,
    config_hash bytea NOT NULL,
    created_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, connection_id) REFERENCES connections(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (connection_id, revision_number),
    UNIQUE (workspace_id, connection_id, id),
    UNIQUE (workspace_id, id)
);

CREATE TABLE connection_project_access (
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    project_id uuid NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    granted_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, connection_id) REFERENCES connections(workspace_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE CASCADE,
    PRIMARY KEY (connection_id, project_id)
);

CREATE TABLE credentials (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    name text NOT NULL,
    auth_scheme text NOT NULL CHECK (auth_scheme IN ('NONE','API_KEY','BEARER_TOKEN','BASIC_AUTH','CUSTOM_HEADER','OAUTH2')),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED','ARCHIVED')),
    current_revision_id uuid,
    active_secret_version_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    FOREIGN KEY (workspace_id, connection_id) REFERENCES connections(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, connection_id, id),
    UNIQUE (workspace_id, id)
);

CREATE TABLE credential_revisions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    credential_id uuid NOT NULL,
    revision_number bigint NOT NULL CHECK (revision_number > 0),
    auth_scheme text NOT NULL CHECK (auth_scheme IN ('NONE','API_KEY','BEARER_TOKEN','BASIC_AUTH','CUSTOM_HEADER','OAUTH2')),
    config_json jsonb NOT NULL,
    config_hash bytea NOT NULL,
    created_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, connection_id, credential_id)
        REFERENCES credentials(workspace_id, connection_id, id) ON DELETE RESTRICT,
    UNIQUE (credential_id, revision_number),
    UNIQUE (workspace_id, connection_id, credential_id, id),
    UNIQUE (workspace_id, credential_id, id),
    UNIQUE (workspace_id, id)
);

CREATE TABLE credential_secret_versions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    credential_id uuid NOT NULL,
    version_number bigint NOT NULL CHECK (version_number > 0),
    status text NOT NULL CHECK (status IN ('PENDING','ACTIVE','RETIRING','REVOKED','DESTROYED')),
    ciphertext bytea,
    wrapped_dek bytea,
    kms_key_ref text,
    encryption_algorithm text,
    nonce bytea,
    safe_hint text,
    activated_at timestamptz,
    revoked_at timestamptz,
    destroyed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, connection_id, credential_id)
        REFERENCES credentials(workspace_id, connection_id, id) ON DELETE RESTRICT,
    CHECK ((status = 'DESTROYED' AND ciphertext IS NULL) OR status <> 'DESTROYED'),
    UNIQUE (credential_id, version_number),
    UNIQUE (workspace_id, connection_id, credential_id, id),
    UNIQUE (workspace_id, credential_id, id),
    UNIQUE (workspace_id, id)
);

ALTER TABLE credentials
    ADD CONSTRAINT fk_credentials_current_revision
        FOREIGN KEY (workspace_id, connection_id, id, current_revision_id)
        REFERENCES credential_revisions(workspace_id, connection_id, credential_id, id)
        DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT fk_credentials_active_secret
        FOREIGN KEY (workspace_id, connection_id, id, active_secret_version_id)
        REFERENCES credential_secret_versions(workspace_id, connection_id, credential_id, id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE oauth_token_states (
    credential_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    encrypted_access_token bytea,
    encrypted_refresh_token bytea,
    wrapped_dek bytea,
    kms_key_ref text,
    expires_at timestamptz,
    refresh_version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, connection_id, credential_id)
        REFERENCES credentials(workspace_id, connection_id, id) ON DELETE CASCADE
);

CREATE TABLE operations (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','DISABLED','ARCHIVED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    FOREIGN KEY (workspace_id, connection_id) REFERENCES connections(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, connection_id, id),
    UNIQUE (workspace_id, id)
);


CREATE TABLE operation_drafts (
    operation_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    draft_json jsonb NOT NULL,
    updated_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, connection_id, operation_id)
        REFERENCES operations(workspace_id, connection_id, id) ON DELETE CASCADE
);

CREATE TABLE operation_versions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    version_number bigint NOT NULL CHECK (version_number > 0),
    definition_schema_version integer NOT NULL CHECK (definition_schema_version > 0),
    effect text NOT NULL CHECK (effect IN ('READ','WRITE')),
    request_body_mode text NOT NULL CHECK (request_body_mode IN ('NONE','JSON','FORM_URLENCODED','MULTIPART','RAW')),
    response_mode text NOT NULL CHECK (response_mode IN ('JSON','TEXT','BINARY','STREAM')),
    definition_json jsonb NOT NULL,
    definition_hash bytea NOT NULL,
    created_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, connection_id, operation_id)
        REFERENCES operations(workspace_id, connection_id, id) ON DELETE RESTRICT,
    UNIQUE (operation_id, version_number),
    UNIQUE (workspace_id, connection_id, operation_id, id),
    UNIQUE (workspace_id, operation_id, id),
    UNIQUE (workspace_id, id)
);

-- -----------------------------------------------------------------------------
-- Bindings
-- -----------------------------------------------------------------------------

CREATE TABLE bindings (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('QUERY','ACTION')),
    exposure_mode text NOT NULL CHECK (exposure_mode IN ('PUBLIC','INTERNAL')),
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','DISABLED','ARCHIVED')),
    active_revision_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, project_id, id),
    UNIQUE (workspace_id, project_id, id, exposure_mode),
    UNIQUE (workspace_id, id)
);


CREATE TABLE binding_drafts (
    binding_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    draft_json jsonb NOT NULL,
    updated_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, binding_id)
        REFERENCES bindings(workspace_id, project_id, id) ON DELETE CASCADE
);

CREATE TABLE binding_revisions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    binding_id uuid NOT NULL,
    revision_number bigint NOT NULL CHECK (revision_number > 0),
    connection_id uuid NOT NULL,
    connection_revision_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    operation_version_id uuid NOT NULL,
    credential_id uuid NOT NULL,
    credential_revision_id uuid NOT NULL,
    input_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    origin_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    cache_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    rate_limit_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    runtime_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    idempotency_policy text NOT NULL DEFAULT 'DISABLED' CHECK (idempotency_policy IN ('DISABLED','SUPPORTED','REQUIRED')),
    compiled_config_json jsonb NOT NULL,
    config_hash bytea NOT NULL,
    created_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, binding_id)
        REFERENCES bindings(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, connection_id, connection_revision_id)
        REFERENCES connection_revisions(workspace_id, connection_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, connection_id, operation_id, operation_version_id)
        REFERENCES operation_versions(workspace_id, connection_id, operation_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, connection_id, credential_id, credential_revision_id)
        REFERENCES credential_revisions(workspace_id, connection_id, credential_id, id) ON DELETE RESTRICT,
    UNIQUE (binding_id, revision_number),
    UNIQUE (workspace_id, project_id, binding_id, id),
    UNIQUE (
        workspace_id,
        project_id,
        binding_id,
        id,
        connection_id,
        connection_revision_id,
        operation_id,
        operation_version_id,
        credential_id,
        credential_revision_id
    ),
    UNIQUE (workspace_id, binding_id, id),
    UNIQUE (workspace_id, id)
);

ALTER TABLE bindings
    ADD CONSTRAINT fk_bindings_active_revision
        FOREIGN KEY (workspace_id, project_id, id, active_revision_id)
        REFERENCES binding_revisions(workspace_id, project_id, binding_id, id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE binding_public_identifiers (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    binding_id uuid NOT NULL,
    binding_exposure_mode text NOT NULL DEFAULT 'PUBLIC'
        CHECK (binding_exposure_mode = 'PUBLIC'),
    public_id text NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    FOREIGN KEY (workspace_id, project_id, binding_id, binding_exposure_mode)
        REFERENCES bindings(workspace_id, project_id, id, exposure_mode) ON DELETE RESTRICT,
    UNIQUE (public_id),
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_binding_public_identifiers_active
    ON binding_public_identifiers(binding_id) WHERE revoked_at IS NULL;

-- -----------------------------------------------------------------------------
-- Idempotency / Execution
-- -----------------------------------------------------------------------------

CREATE TABLE executions (
    id uuid PRIMARY KEY,
    public_execution_ref text NOT NULL,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id uuid NOT NULL,
    lineage_mode text NOT NULL CHECK (lineage_mode IN ('BINDING','DIRECT')),
    binding_id uuid,
    binding_revision_id uuid,
    operation_id uuid NOT NULL,
    operation_version_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    connection_revision_id uuid NOT NULL,
    credential_id uuid NOT NULL,
    credential_revision_id uuid NOT NULL,
    source text NOT NULL CHECK (source IN ('QUERY','ACTION','JOB','WEBHOOK','SYNC','MANUAL_TEST','MANUAL_REPLAY','INTERNAL')),
    status text NOT NULL CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','REJECTED','FAILED','INDETERMINATE','CANCELLED','DEAD_LETTERED')),
    replay_of_execution_id uuid REFERENCES executions(id) ON DELETE RESTRICT,
    job_run_id uuid,
    webhook_delivery_id uuid,
    sync_run_id uuid,
    sync_run_item_id uuid,
    lease_id uuid,
    lease_expires_at timestamptz,
    current_attempt_number integer NOT NULL DEFAULT 0 CHECK (current_attempt_number >= 0),
    payload_ref text,
    request_content_type text,
    response_content_type text,
    request_bytes bigint CHECK (request_bytes IS NULL OR request_bytes >= 0),
    response_bytes bigint CHECK (response_bytes IS NULL OR response_bytes >= 0),
    trace_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    CHECK (
        (lineage_mode = 'BINDING' AND binding_id IS NOT NULL AND binding_revision_id IS NOT NULL)
        OR
        (lineage_mode = 'DIRECT' AND binding_id IS NULL AND binding_revision_id IS NULL)
    ),
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, project_id, binding_id)
        REFERENCES bindings(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, connection_id, connection_revision_id)
        REFERENCES connection_revisions(workspace_id, connection_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, connection_id, operation_id, operation_version_id)
        REFERENCES operation_versions(workspace_id, connection_id, operation_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, connection_id, credential_id, credential_revision_id)
        REFERENCES credential_revisions(workspace_id, connection_id, credential_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (
        workspace_id,
        project_id,
        binding_id,
        binding_revision_id,
        connection_id,
        connection_revision_id,
        operation_id,
        operation_version_id,
        credential_id,
        credential_revision_id
    )
        REFERENCES binding_revisions(
            workspace_id,
            project_id,
            binding_id,
            id,
            connection_id,
            connection_revision_id,
            operation_id,
            operation_version_id,
            credential_id,
            credential_revision_id
        ) ON DELETE RESTRICT,
    UNIQUE (public_execution_ref),
    UNIQUE (workspace_id, id)
);

CREATE TABLE execution_attempts (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    execution_id uuid NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    status text NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','FAILED','INDETERMINATE','CANCELLED')),
    lease_id uuid,
    credential_secret_version_id uuid,
    upstream_status integer,
    request_sent_at timestamptz,
    response_received_at timestamptz,
    duration_ms bigint CHECK (duration_ms IS NULL OR duration_ms >= 0),
    request_bytes bigint CHECK (request_bytes IS NULL OR request_bytes >= 0),
    response_bytes bigint CHECK (response_bytes IS NULL OR response_bytes >= 0),
    error_category text,
    error_code text,
    retryable boolean,
    trace_id text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    FOREIGN KEY (workspace_id, execution_id) REFERENCES executions(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, credential_secret_version_id)
        REFERENCES credential_secret_versions(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (execution_id, attempt_number),
    UNIQUE (workspace_id, id)
);

CREATE TABLE idempotency_records (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    binding_id uuid NOT NULL,
    key_hash bytea NOT NULL,
    request_hash bytea NOT NULL,
    binding_revision_id uuid NOT NULL,
    execution_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('PROCESSING','SUCCEEDED','FAILED','INDETERMINATE')),
    response_status integer,
    response_ref text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, binding_id) REFERENCES bindings(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, binding_id, binding_revision_id)
        REFERENCES binding_revisions(workspace_id, binding_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, execution_id) REFERENCES executions(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, binding_id, key_hash),
    UNIQUE (workspace_id, id),
    CHECK (expires_at > created_at)
);

-- -----------------------------------------------------------------------------
-- Sync definitions are declared before Jobs so JobRevision can target them.
-- -----------------------------------------------------------------------------

CREATE TABLE sync_definitions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','PAUSED','ARCHIVED')),
    active_revision_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, project_id, id),
    UNIQUE (workspace_id, id)
);

CREATE TABLE sync_drafts (
    sync_definition_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    draft_json jsonb NOT NULL,
    updated_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, sync_definition_id)
        REFERENCES sync_definitions(workspace_id, project_id, id) ON DELETE CASCADE
);

CREATE TABLE sync_revisions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    sync_definition_id uuid NOT NULL,
    revision_number bigint NOT NULL CHECK (revision_number > 0),
    source_adapter_key text NOT NULL,
    source_config_json jsonb NOT NULL,
    target_adapter_key text NOT NULL,
    target_config_json jsonb NOT NULL,
    source_binding_id uuid,
    target_binding_id uuid,
    identity_strategy_json jsonb NOT NULL,
    mapping_json jsonb NOT NULL,
    source_schema_fingerprint bytea,
    target_schema_fingerprint bytea,
    scan_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    conflict_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    missing_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    destructive_guard_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    publication_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    config_hash bytea NOT NULL,
    created_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, sync_definition_id)
        REFERENCES sync_definitions(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, source_binding_id) REFERENCES bindings(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, target_binding_id) REFERENCES bindings(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (sync_definition_id, revision_number),
    UNIQUE (workspace_id, project_id, sync_definition_id, id),
    UNIQUE (workspace_id, sync_definition_id, id),
    UNIQUE (workspace_id, id)
);

ALTER TABLE sync_definitions
    ADD CONSTRAINT fk_sync_definitions_active_revision
        FOREIGN KEY (workspace_id, project_id, id, active_revision_id)
        REFERENCES sync_revisions(workspace_id, project_id, sync_definition_id, id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE sync_checkpoints (
    sync_definition_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    sync_revision_id uuid NOT NULL,
    cursor_json jsonb,
    watermark text,
    advanced_at timestamptz,
    run_id uuid,
    FOREIGN KEY (workspace_id, project_id, sync_definition_id)
        REFERENCES sync_definitions(workspace_id, project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, sync_definition_id, sync_revision_id)
        REFERENCES sync_revisions(workspace_id, sync_definition_id, id) ON DELETE RESTRICT
);

CREATE TABLE sync_mappings (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    sync_definition_id uuid NOT NULL,
    source_identity_hash bytea NOT NULL,
    source_identity_hint text,
    target_namespace text,
    target_identity text,
    target_exclusive_key text,
    last_source_hash bytea,
    last_target_hash bytea,
    last_applied_revision_id uuid,
    last_seen_run_id uuid,
    last_synced_run_id uuid,
    state text NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','SOURCE_MISSING','TARGET_MISSING','CONFLICT','DETACHED','DELETED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, sync_definition_id)
        REFERENCES sync_definitions(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, sync_definition_id, last_applied_revision_id)
        REFERENCES sync_revisions(workspace_id, sync_definition_id, id) ON DELETE RESTRICT,
    UNIQUE (sync_definition_id, source_identity_hash),
    UNIQUE (workspace_id, sync_definition_id, id),
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_sync_mappings_target_exclusive
    ON sync_mappings(sync_definition_id, target_exclusive_key)
    WHERE target_exclusive_key IS NOT NULL AND state <> 'DETACHED';

-- -----------------------------------------------------------------------------
-- Jobs / Scheduler
-- -----------------------------------------------------------------------------

CREATE TABLE job_definitions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','PAUSED','ARCHIVED')),
    active_revision_id uuid,
    next_due_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, project_id, id),
    UNIQUE (workspace_id, id)
);


CREATE TABLE job_drafts (
    job_definition_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    draft_json jsonb NOT NULL,
    updated_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, job_definition_id)
        REFERENCES job_definitions(workspace_id, project_id, id) ON DELETE CASCADE
);

CREATE TABLE job_revisions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    job_definition_id uuid NOT NULL,
    revision_number bigint NOT NULL CHECK (revision_number > 0),
    binding_id uuid,
    sync_definition_id uuid,
    schedule_kind text NOT NULL CHECK (schedule_kind IN ('CRON','ONE_TIME')),
    schedule_expression text NOT NULL,
    timezone text NOT NULL,
    starts_at timestamptz,
    ends_at timestamptz,
    misfire_policy text NOT NULL CHECK (misfire_policy IN ('SKIP','RUN_ONCE','CATCH_UP_BOUNDED')),
    max_catch_up integer NOT NULL DEFAULT 1 CHECK (max_catch_up > 0),
    overlap_policy text NOT NULL CHECK (overlap_policy IN ('ALLOW','SKIP_IF_RUNNING','SERIALIZE')),
    input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, job_definition_id)
        REFERENCES job_definitions(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, project_id, binding_id)
        REFERENCES bindings(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, project_id, sync_definition_id)
        REFERENCES sync_definitions(workspace_id, project_id, id) ON DELETE RESTRICT,
    CHECK ((binding_id IS NOT NULL)::integer + (sync_definition_id IS NOT NULL)::integer = 1),
    CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at),
    UNIQUE (job_definition_id, revision_number),
    UNIQUE (workspace_id, project_id, job_definition_id, id),
    UNIQUE (workspace_id, job_definition_id, id),
    UNIQUE (workspace_id, id)
);

ALTER TABLE job_definitions
    ADD CONSTRAINT fk_job_definitions_active_revision
        FOREIGN KEY (workspace_id, project_id, id, active_revision_id)
        REFERENCES job_revisions(workspace_id, project_id, job_definition_id, id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE job_runs (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    job_definition_id uuid NOT NULL,
    job_revision_id uuid NOT NULL,
    scheduled_for timestamptz NOT NULL,
    binding_id uuid,
    binding_revision_id uuid,
    sync_definition_id uuid,
    sync_revision_id uuid,
    status text NOT NULL CHECK (status IN ('PENDING','QUEUED','RUNNING','SUCCEEDED','FAILED','INDETERMINATE','SKIPPED','CANCELLED','DEAD_LETTERED')),
    input_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    FOREIGN KEY (workspace_id, project_id, job_definition_id)
        REFERENCES job_definitions(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, job_definition_id, job_revision_id)
        REFERENCES job_revisions(workspace_id, job_definition_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, project_id, binding_id, binding_revision_id)
        REFERENCES binding_revisions(workspace_id, project_id, binding_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, project_id, sync_definition_id, sync_revision_id)
        REFERENCES sync_revisions(workspace_id, project_id, sync_definition_id, id) ON DELETE RESTRICT,
    CHECK (
        (binding_id IS NOT NULL AND binding_revision_id IS NOT NULL AND sync_definition_id IS NULL AND sync_revision_id IS NULL)
        OR
        (binding_id IS NULL AND binding_revision_id IS NULL AND sync_definition_id IS NOT NULL AND sync_revision_id IS NOT NULL)
    ),
    UNIQUE (job_definition_id, scheduled_for),
    UNIQUE (workspace_id, id)
);

-- -----------------------------------------------------------------------------
-- Webhooks
-- -----------------------------------------------------------------------------

CREATE TABLE webhook_endpoints (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','DISABLED','ARCHIVED')),
    active_revision_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz,
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, project_id, id),
    UNIQUE (workspace_id, id)
);


CREATE TABLE webhook_endpoint_drafts (
    webhook_endpoint_id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    draft_json jsonb NOT NULL,
    updated_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, webhook_endpoint_id)
        REFERENCES webhook_endpoints(workspace_id, project_id, id) ON DELETE CASCADE
);

CREATE TABLE webhook_endpoint_revisions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    webhook_endpoint_id uuid NOT NULL,
    revision_number bigint NOT NULL CHECK (revision_number > 0),
    binding_id uuid NOT NULL,
    verification_scheme text NOT NULL,
    verification_config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    event_id_rule_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    replay_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    event_filter_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    payload_mapping_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    ingress_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    payload_retention_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    config_hash bytea NOT NULL,
    created_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, webhook_endpoint_id)
        REFERENCES webhook_endpoints(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, project_id, binding_id)
        REFERENCES bindings(workspace_id, project_id, id) ON DELETE RESTRICT,
    UNIQUE (webhook_endpoint_id, revision_number),
    UNIQUE (workspace_id, project_id, webhook_endpoint_id, id),
    UNIQUE (workspace_id, webhook_endpoint_id, id),
    UNIQUE (workspace_id, id)
);

ALTER TABLE webhook_endpoints
    ADD CONSTRAINT fk_webhook_endpoints_active_revision
        FOREIGN KEY (workspace_id, project_id, id, active_revision_id)
        REFERENCES webhook_endpoint_revisions(workspace_id, project_id, webhook_endpoint_id, id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE webhook_public_identifiers (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    webhook_endpoint_id uuid NOT NULL,
    public_id text NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    FOREIGN KEY (workspace_id, project_id, webhook_endpoint_id)
        REFERENCES webhook_endpoints(workspace_id, project_id, id) ON DELETE RESTRICT,
    UNIQUE (public_id),
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_webhook_public_identifiers_active
    ON webhook_public_identifiers(webhook_endpoint_id) WHERE revoked_at IS NULL;

CREATE TABLE webhook_endpoint_secret_versions (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    webhook_endpoint_id uuid NOT NULL,
    version_number bigint NOT NULL CHECK (version_number > 0),
    status text NOT NULL CHECK (status IN ('PENDING','ACTIVE','RETIRING','REVOKED','DESTROYED')),
    ciphertext bytea,
    wrapped_dek bytea,
    kms_key_ref text,
    nonce bytea,
    safe_hint text,
    activated_at timestamptz,
    revoked_at timestamptz,
    destroyed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id, webhook_endpoint_id)
        REFERENCES webhook_endpoints(workspace_id, project_id, id) ON DELETE RESTRICT,
    CHECK ((status = 'DESTROYED' AND ciphertext IS NULL) OR status <> 'DESTROYED'),
    UNIQUE (webhook_endpoint_id, version_number),
    UNIQUE (workspace_id, id)
);

CREATE TABLE webhook_deliveries (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    webhook_endpoint_id uuid NOT NULL,
    webhook_endpoint_revision_id uuid NOT NULL,
    provider_event_id text,
    provider_event_type text,
    payload_hash bytea NOT NULL,
    payload_size bigint NOT NULL CHECK (payload_size >= 0),
    content_type text,
    payload_ref text,
    payload_purged_at timestamptz,
    binding_id uuid NOT NULL,
    binding_revision_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('ACCEPTED','PROCESSING','SUCCEEDED','FAILED','IGNORED','DEAD_LETTERED')),
    receive_count integer NOT NULL DEFAULT 1 CHECK (receive_count > 0),
    provider_timestamp timestamptz,
    received_at timestamptz NOT NULL DEFAULT now(),
    accepted_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    last_error_code text,
    CHECK (payload_ref IS NOT NULL OR payload_purged_at IS NOT NULL),
    FOREIGN KEY (workspace_id, project_id, webhook_endpoint_id)
        REFERENCES webhook_endpoints(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, webhook_endpoint_id, webhook_endpoint_revision_id)
        REFERENCES webhook_endpoint_revisions(workspace_id, webhook_endpoint_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, project_id, binding_id, binding_revision_id)
        REFERENCES binding_revisions(workspace_id, project_id, binding_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_webhook_deliveries_provider_event
    ON webhook_deliveries(webhook_endpoint_id, provider_event_id)
    WHERE provider_event_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- Sync runtime
-- -----------------------------------------------------------------------------

CREATE TABLE sync_runs (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    sync_definition_id uuid NOT NULL,
    sync_revision_id uuid NOT NULL,
    job_run_id uuid,
    trigger text NOT NULL CHECK (trigger IN ('MANUAL','SCHEDULED','WEBHOOK','API','SYSTEM')),
    scan_mode text NOT NULL CHECK (scan_mode IN ('FULL','INCREMENTAL')),
    execution_mode text NOT NULL CHECK (execution_mode IN ('DRY_RUN','APPLY')),
    status text NOT NULL CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','PARTIAL','BLOCKED','REQUIRES_CONFIRMATION','FAILED','CANCELLED','DEAD_LETTERED')),
    source_binding_id uuid,
    source_binding_revision_id uuid,
    target_binding_id uuid,
    target_binding_revision_id uuid,
    scanned_count bigint NOT NULL DEFAULT 0 CHECK (scanned_count >= 0),
    created_count bigint NOT NULL DEFAULT 0 CHECK (created_count >= 0),
    updated_count bigint NOT NULL DEFAULT 0 CHECK (updated_count >= 0),
    unchanged_count bigint NOT NULL DEFAULT 0 CHECK (unchanged_count >= 0),
    deleted_count bigint NOT NULL DEFAULT 0 CHECK (deleted_count >= 0),
    skipped_count bigint NOT NULL DEFAULT 0 CHECK (skipped_count >= 0),
    failed_count bigint NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    conflict_count bigint NOT NULL DEFAULT 0 CHECK (conflict_count >= 0),
    publication_status text CHECK (publication_status IN ('NOT_REQUESTED','PENDING','SUCCEEDED','FAILED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    FOREIGN KEY (workspace_id, project_id, sync_definition_id)
        REFERENCES sync_definitions(workspace_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, sync_definition_id, sync_revision_id)
        REFERENCES sync_revisions(workspace_id, sync_definition_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, job_run_id) REFERENCES job_runs(workspace_id, id) ON DELETE RESTRICT,
    CHECK (
        (source_binding_id IS NULL AND source_binding_revision_id IS NULL)
        OR
        (source_binding_id IS NOT NULL AND source_binding_revision_id IS NOT NULL)
    ),
    CHECK (
        (target_binding_id IS NULL AND target_binding_revision_id IS NULL)
        OR
        (target_binding_id IS NOT NULL AND target_binding_revision_id IS NOT NULL)
    ),
    FOREIGN KEY (workspace_id, project_id, source_binding_id, source_binding_revision_id)
        REFERENCES binding_revisions(workspace_id, project_id, binding_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, project_id, target_binding_id, target_binding_revision_id)
        REFERENCES binding_revisions(workspace_id, project_id, binding_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_sync_runs_one_active
    ON sync_runs(sync_definition_id)
    WHERE status IN ('PENDING','RUNNING','REQUIRES_CONFIRMATION');

CREATE TABLE sync_run_items (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    sync_run_id uuid NOT NULL,
    sync_mapping_id uuid,
    source_identity_hash bytea NOT NULL,
    source_identity_hint text,
    action text NOT NULL CHECK (action IN ('CREATE','UPDATE','NO_CHANGE','DELETE','SOFT_DELETE','SKIP','CONFLICT','TARGET_SPECIFIC')),
    adapter_action text,
    status text NOT NULL CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','INDETERMINATE')),
    source_hash bytea,
    target_identity text,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    FOREIGN KEY (workspace_id, sync_run_id) REFERENCES sync_runs(workspace_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (workspace_id, sync_mapping_id) REFERENCES sync_mappings(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (sync_run_id, source_identity_hash),
    UNIQUE (workspace_id, id)
);

ALTER TABLE sync_checkpoints
    ADD CONSTRAINT fk_sync_checkpoints_run
        FOREIGN KEY (workspace_id, run_id) REFERENCES sync_runs(workspace_id, id) ON DELETE SET NULL;
ALTER TABLE sync_mappings
    ADD CONSTRAINT fk_sync_mappings_last_seen_run
        FOREIGN KEY (workspace_id, last_seen_run_id) REFERENCES sync_runs(workspace_id, id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_sync_mappings_last_synced_run
        FOREIGN KEY (workspace_id, last_synced_run_id) REFERENCES sync_runs(workspace_id, id) ON DELETE SET NULL;

-- Now that JobRun/WebhookDelivery/SyncRunItem exist, complete Execution provenance FKs.
ALTER TABLE executions
    ADD CONSTRAINT fk_executions_job_run
        FOREIGN KEY (workspace_id, job_run_id) REFERENCES job_runs(workspace_id, id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_executions_webhook_delivery
        FOREIGN KEY (workspace_id, webhook_delivery_id) REFERENCES webhook_deliveries(workspace_id, id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_executions_sync_run
        FOREIGN KEY (workspace_id, sync_run_id) REFERENCES sync_runs(workspace_id, id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_executions_sync_run_item
        FOREIGN KEY (workspace_id, sync_run_item_id) REFERENCES sync_run_items(workspace_id, id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uq_executions_webhook_original
    ON executions(webhook_delivery_id)
    WHERE webhook_delivery_id IS NOT NULL AND replay_of_execution_id IS NULL;
CREATE UNIQUE INDEX uq_executions_job_original
    ON executions(job_run_id)
    WHERE job_run_id IS NOT NULL AND replay_of_execution_id IS NULL;

-- -----------------------------------------------------------------------------
-- Transactional Outbox / Consumer dedupe
-- -----------------------------------------------------------------------------

CREATE TABLE outbox_events (
    id uuid PRIMARY KEY,
    workspace_id uuid,
    topic text NOT NULL,
    event_type text NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version > 0),
    aggregate_type text NOT NULL,
    aggregate_id uuid,
    payload_json jsonb NOT NULL,
    headers_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','PROCESSING','PUBLISHED','FAILED','DEAD_LETTERED')),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_id uuid,
    lease_expires_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    published_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE RESTRICT
);

CREATE TABLE consumer_deduplication (
    consumer_name text NOT NULL,
    message_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (consumer_name, message_id)
);

-- -----------------------------------------------------------------------------
-- Notifications
-- -----------------------------------------------------------------------------

CREATE TABLE notifications (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id uuid,
    notification_type text NOT NULL,
    priority text NOT NULL CHECK (priority IN ('CRITICAL','TRANSACTIONAL','NORMAL')),
    status text NOT NULL CHECK (status IN ('PENDING','PROCESSING','PARTIALLY_DELIVERED','DELIVERED','FAILED','EXPIRED')),
    source_event_id uuid,
    source_aggregate_type text,
    source_aggregate_id uuid,
    dedupe_key text NOT NULL,
    recipient_intent_json jsonb NOT NULL,
    template_key text NOT NULL,
    template_version integer NOT NULL CHECK (template_version > 0),
    not_before timestamptz,
    expires_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, notification_type, dedupe_key),
    UNIQUE (workspace_id, id),
    CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE TABLE notification_deliveries (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    notification_id uuid NOT NULL,
    channel text NOT NULL CHECK (channel IN ('EMAIL','IN_APP')),
    status text NOT NULL CHECK (status IN ('PENDING','PROCESSING','PROVIDER_ACCEPTED','DELIVERED','FAILED','BOUNCED','COMPLAINED','EXPIRED')),
    destination_snapshot text,
    template_key text NOT NULL,
    template_version integer NOT NULL CHECK (template_version > 0),
    rendered_content_ref text,
    provider_key text,
    provider_message_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    accepted_at timestamptz,
    delivered_at timestamptz,
    failed_at timestamptz,
    read_at timestamptz,
    dismissed_at timestamptz,
    FOREIGN KEY (workspace_id, notification_id) REFERENCES notifications(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (workspace_id, id)
);
CREATE UNIQUE INDEX uq_notification_provider_message
    ON notification_deliveries(provider_key, provider_message_id)
    WHERE provider_key IS NOT NULL AND provider_message_id IS NOT NULL;

CREATE TABLE notification_delivery_attempts (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    notification_delivery_id uuid NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    provider_key text,
    status text NOT NULL CHECK (status IN ('RUNNING','PROVIDER_ACCEPTED','DELIVERED','FAILED','INDETERMINATE','EXPIRED')),
    error_code text,
    error_category text,
    retryable boolean,
    provider_metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    trace_id text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    FOREIGN KEY (workspace_id, notification_delivery_id)
        REFERENCES notification_deliveries(workspace_id, id) ON DELETE RESTRICT,
    UNIQUE (notification_delivery_id, attempt_number),
    UNIQUE (workspace_id, id)
);

CREATE TABLE notification_preferences (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    notification_type text NOT NULL,
    channel text NOT NULL CHECK (channel IN ('EMAIL','IN_APP')),
    enabled boolean NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, user_id, notification_type, channel),
    UNIQUE (workspace_id, id)
);

-- -----------------------------------------------------------------------------
-- Audit
-- -----------------------------------------------------------------------------

CREATE TABLE support_sessions (
    id uuid PRIMARY KEY,
    support_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    target_workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    target_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    reason text NOT NULL,
    ticket_ref text,
    scope_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    ended_at timestamptz,
    CHECK (expires_at > started_at)
);

CREATE TABLE audit_events (
    id uuid PRIMARY KEY,
    workspace_id uuid REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id uuid,
    scope text NOT NULL CHECK (scope IN ('TENANT','PLATFORM')),
    actor_type text NOT NULL CHECK (actor_type IN ('USER','SERVICE','SYSTEM','SUPPORT')),
    actor_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    actor_service_key text,
    actor_display_snapshot text,
    actor_role_snapshot text,
    effective_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    support_session_id uuid REFERENCES support_sessions(id) ON DELETE RESTRICT,
    action text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('SUCCEEDED','FAILED','DENIED')),
    resource_type text NOT NULL,
    resource_id uuid,
    resource_display_snapshot text,
    before_json jsonb,
    after_json jsonb,
    change_json jsonb,
    request_id text,
    trace_id text,
    session_id text,
    surface text NOT NULL CHECK (surface IN ('WEB_DASHBOARD','FRAMER_PLUGIN','PUBLIC_API','INTERNAL_API','PLATFORM_OPS','SYSTEM_WORKER')),
    ip_address inet,
    user_agent_summary text,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    correction_of_event_id uuid REFERENCES audit_events(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, project_id) REFERENCES projects(workspace_id, id) ON DELETE RESTRICT,
    CHECK ((scope = 'TENANT' AND workspace_id IS NOT NULL) OR scope = 'PLATFORM')
);

-- -----------------------------------------------------------------------------
-- Operational indexes
-- -----------------------------------------------------------------------------

CREATE INDEX idx_projects_workspace_status ON projects(workspace_id, status);
CREATE INDEX idx_projects_workspace_created_id ON projects(workspace_id, created_at DESC, id DESC);
CREATE INDEX idx_connections_workspace_status ON connections(workspace_id, status);
CREATE INDEX idx_credentials_workspace_connection_status ON credentials(workspace_id, connection_id, status);
CREATE INDEX idx_operations_workspace_connection_status ON operations(workspace_id, connection_id, status);
CREATE INDEX idx_bindings_project_status ON bindings(project_id, status);

CREATE INDEX idx_executions_workspace_created ON executions(workspace_id, created_at DESC);
CREATE INDEX idx_executions_project_created ON executions(project_id, created_at DESC);
CREATE INDEX idx_executions_binding_created ON executions(binding_id, created_at DESC);
CREATE INDEX idx_executions_status_created ON executions(status, created_at);
CREATE INDEX idx_executions_trace_id ON executions(trace_id) WHERE trace_id IS NOT NULL;
CREATE INDEX idx_execution_attempts_execution ON execution_attempts(execution_id, attempt_number);
CREATE INDEX idx_idempotency_records_expires ON idempotency_records(expires_at);

CREATE INDEX idx_job_definitions_due ON job_definitions(status, next_due_at) WHERE status = 'ACTIVE';
CREATE INDEX idx_job_runs_workspace_created ON job_runs(workspace_id, created_at DESC);
CREATE INDEX idx_job_runs_definition_scheduled ON job_runs(job_definition_id, scheduled_for DESC);
CREATE INDEX idx_job_runs_status_created ON job_runs(status, created_at);

CREATE INDEX idx_webhook_deliveries_workspace_received ON webhook_deliveries(workspace_id, received_at DESC);
CREATE INDEX idx_webhook_deliveries_endpoint_received ON webhook_deliveries(webhook_endpoint_id, received_at DESC);
CREATE INDEX idx_webhook_deliveries_status_received ON webhook_deliveries(status, received_at);

CREATE INDEX idx_sync_runs_workspace_created ON sync_runs(workspace_id, created_at DESC);
CREATE INDEX idx_sync_runs_definition_created ON sync_runs(sync_definition_id, created_at DESC);
CREATE INDEX idx_sync_run_items_run_status ON sync_run_items(sync_run_id, status);
CREATE INDEX idx_sync_mappings_definition_state ON sync_mappings(sync_definition_id, state);

CREATE INDEX idx_outbox_dispatch ON outbox_events(status, available_at, created_at)
    WHERE status IN ('PENDING','PROCESSING','FAILED');
CREATE INDEX idx_outbox_lease_expiry ON outbox_events(lease_expires_at)
    WHERE status = 'PROCESSING';
CREATE INDEX idx_outbox_published_purge ON outbox_events(published_at)
    WHERE status = 'PUBLISHED';
CREATE INDEX idx_consumer_deduplication_processed ON consumer_deduplication(processed_at);

CREATE INDEX idx_notifications_workspace_created ON notifications(workspace_id, created_at DESC);
CREATE INDEX idx_notifications_expires ON notifications(expires_at)
    WHERE expires_at IS NOT NULL AND status NOT IN ('DELIVERED','FAILED','EXPIRED');
CREATE INDEX idx_notification_deliveries_status_created ON notification_deliveries(status, created_at);

CREATE INDEX idx_usage_events_workspace_occurred ON usage_events(workspace_id, occurred_at DESC);
CREATE INDEX idx_usage_events_project_occurred ON usage_events(project_id, occurred_at DESC) WHERE project_id IS NOT NULL;

CREATE INDEX idx_audit_workspace_created ON audit_events(workspace_id, created_at DESC) WHERE workspace_id IS NOT NULL;
CREATE INDEX idx_audit_project_created ON audit_events(workspace_id, project_id, created_at DESC) WHERE project_id IS NOT NULL;
CREATE INDEX idx_audit_actor_created ON audit_events(workspace_id, actor_user_id, created_at DESC) WHERE actor_user_id IS NOT NULL;
CREATE INDEX idx_audit_resource_created ON audit_events(workspace_id, resource_type, resource_id, created_at DESC);
CREATE INDEX idx_audit_action_created ON audit_events(workspace_id, action, created_at DESC);
CREATE INDEX idx_audit_request_id ON audit_events(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX idx_audit_trace_id ON audit_events(trace_id) WHERE trace_id IS NOT NULL;
CREATE INDEX idx_audit_support_session ON audit_events(support_session_id) WHERE support_session_id IS NOT NULL;

COMMIT;

-- -----------------------------------------------------------------------------
-- Rules intentionally enforced in domain services rather than pure DDL
-- -----------------------------------------------------------------------------
-- 1. ACTIVE Workspace must retain >= 1 active OWNER.
-- 2. Binding PUBLIC/INTERNAL public-identifier ownership is DB-enforced in V2.
-- 3. QUERY Binding cannot publish a WRITE OperationVersion.
-- 4. Binding publication validates Project -> Connection access and all JSON contracts.
-- 5. Lifecycle/admission checks override cached immutable artifacts.
-- 6. Immutable revision/history write protection is reinforced by database roles in docs/security/database-roles.sql.
-- 7. Job target columns in JobRun must match its JobRevision target; scheduler service enforces this.
-- 8. Webhook verification/dedupe acceptance happens before Delivery persistence/ACK.
-- 9. Sync adapter capabilities, schema compatibility, mark-and-sweep and destructive guards are runtime/domain invariants.
-- 10. Notification REQUIRED preference semantics and provider state monotonicity are domain invariants.
-- 11. Audit payload redaction is mandatory before INSERT.
-- 12. Exact retention/partitioning durations are deferred; V2 includes sweep indexes for known retention keys.
