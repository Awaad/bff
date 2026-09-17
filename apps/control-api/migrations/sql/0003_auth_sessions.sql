-- Add durable local control-plane session admission state.
--
-- This table stores session identity/lifecycle metadata only. It never stores
-- access tokens, refresh tokens, authorization codes, or raw JWTs.

CREATE TABLE app.auth_sessions (
    id uuid PRIMARY KEY,
    user_auth_identity_id uuid NOT NULL
        REFERENCES app.user_auth_identities(id) ON DELETE RESTRICT,
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
    ON app.auth_sessions(user_auth_identity_id)
    WHERE revoked_at IS NULL;

CREATE INDEX ix_auth_sessions_active_expiry
    ON app.auth_sessions(expires_at)
    WHERE revoked_at IS NULL;

-- Existing deployments may already have application roles/default privileges.
-- The previous default policy grants worker SELECT on future tables, so revoke
-- explicitly here. Fresh databases receive the current application-role policy
-- after migrations.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_control_writer') THEN
        EXECUTE 'GRANT SELECT, INSERT ON TABLE app.auth_sessions TO bff_control_writer';
        EXECUTE 'REVOKE UPDATE, DELETE ON TABLE app.auth_sessions FROM bff_control_writer';
        EXECUTE 'GRANT UPDATE (revoked_at, revocation_reason, provider_revoked_at, updated_at) ON TABLE app.auth_sessions TO bff_control_writer';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_runtime_writer') THEN
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE app.auth_sessions FROM bff_runtime_writer';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_worker_writer') THEN
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE app.auth_sessions FROM bff_worker_writer';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_retention') THEN
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE app.auth_sessions FROM bff_retention';
    END IF;
END $$;
