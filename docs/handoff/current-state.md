# Current Engineering State

Last updated: 2026-09-21

## Current baseline

The repository foundation, provider-neutral control-plane authentication, structured
HTTP transport, local developer bootstrap, and first Workspace authorization slice
are implemented.

The current implementation boundary is:

```text
real WorkOS User
-> internal User identity
-> durable AuthSession
-> active WorkspaceMembership
-> authorized Workspace create/list/read
```

The next product domain is Project.

## Implemented

### Repository and database foundation

- Python 3.13 control API with FastAPI and SQLAlchemy async
- PostgreSQL Schema Baseline V2.1 under Alembic
- application database roles and ACL regression tests
- pinned Python and Node dependency graphs
- CI quality and PostgreSQL regression workflows
- OpenTelemetry process lifecycle plumbing
- canonical OpenAPI export and generated TypeScript contract checks
- local Docker Compose infrastructure for PostgreSQL, RabbitMQ, Valkey, and Jaeger

### Authentication and HTTP transport

- exact WorkOS JWT issuer, client ID, algorithm, and JWKS verification
- bounded JWKS refresh for an unknown key ID
- exact `(issuer, subject)` external identity mapping
- durable local AuthSession admission and revocation checks
- first-login WorkOS User lookup and transactional provisioning
- `/v1/auth/session` and `/v1/me`
- RFC 9457 API Problem Details
- request correlation and structured access logging
- live WorkOS PKCE proof covering provisioning, same-`sid` reuse, and `/v1/me`

### Developer bootstrap

- thin root `Makefile` for canonical developer commands
- non-destructive, idempotent `make bootstrap`
- environment and toolchain doctor with duplicate-key and placeholder detection
- documented local and live-WorkOS workflows

### Workspace authorization

- Workspace domain policy and service boundary
- membership-constrained PostgreSQL repository
- transactional Workspace creation with initial OWNER membership and AuditEvent
- authenticated `POST /v1/workspaces`
- authenticated `GET /v1/workspaces`
- authenticated `GET /v1/workspaces/{workspace_id}`
- existence hiding for missing and unauthorized Workspace reads
- unit, transport, PostgreSQL authorization, OpenAPI, and generated-contract coverage

## Current migrations

```text
0001_schema_baseline_v2_1
-> 0002_user_auth_identities
-> 0003_auth_sessions
```

Workspace support uses the existing V2.1 schema and did not require a migration.

## Current verification baseline

GitHub `main` at `af50e042bab464da73e9291fd2f7c78e3f0b7677` has both required
workflows green:

- CI
- Database regression

The hash records the verified baseline at the time of this handoff. GitHub `main`
must still be inspected before starting later work.

## Next build target

Continue Phase 1 in this order:

1. Project
2. Connection
3. Credential and encrypted SecretVersion
4. Operation and immutable OperationVersion
5. Binding and immutable BindingRevision publication
6. PUBLIC runtime endpoint
7. Execution and ExecutionAttempt
8. execution history
9. AuditEvent coverage for each material mutation
10. real PostgreSQL and encrypted-credential E2E proof

The immediate next slice is Project authorization and API implementation,
beginning with review and acceptance of ADR 0021.

## Still not implemented

- Project control-plane API
- Framer authorization and verified Project linking
- Connections, Credentials, Operations, and Bindings
- encrypted credential storage and KMS abstraction
- TypeScript execution runtime
- public runtime admission and execution history
- transactional outbox and RabbitMQ workers
- durable caller/consumer idempotency
- Jobs, Webhooks, Notifications, and Sync
- Dashboard and Framer Plugin product surfaces
- Phase 1 end-to-end vertical-slice proof

Documentation for later domains remains design intent until corresponding code and
tests exist.

## Rules

- no direct cross-domain repository imports
- no raw provider SDKs inside business domains
- no secrets in queue messages or logs
- no broker-as-truth
- no "latest version" runtime joins for immutable historical execution
- reliability paths must be tested under duplicate delivery and failure
- domain authorization must not depend on an HTTP router remembering to enforce it
