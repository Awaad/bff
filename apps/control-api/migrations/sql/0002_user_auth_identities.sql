-- Add provider-neutral external authentication identities.
--
-- This migration may run in two deployment states:
-- 1. application roles already exist from an earlier deployment;
-- 2. a fresh database where role bootstrap runs after Alembic.
--
-- The conditional ACL block secures state (1). The current application-role
-- bootstrap secures state (2).

CREATE TABLE app.user_auth_identities (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES app.users(id) ON DELETE RESTRICT,
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
    ON app.user_auth_identities(user_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_control_writer') THEN
        EXECUTE 'GRANT SELECT, INSERT ON TABLE app.user_auth_identities TO bff_control_writer';
        EXECUTE 'REVOKE UPDATE, DELETE ON TABLE app.user_auth_identities FROM bff_control_writer';
        EXECUTE 'GRANT UPDATE (status, updated_at, disabled_at) ON TABLE app.user_auth_identities TO bff_control_writer';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_runtime_writer') THEN
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE app.user_auth_identities FROM bff_runtime_writer';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_worker_writer') THEN
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE app.user_auth_identities FROM bff_worker_writer';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bff_retention') THEN
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE app.user_auth_identities FROM bff_retention';
    END IF;
END $$;
