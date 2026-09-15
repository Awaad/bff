# Build Sequence

## Phase 0 — repository and foundations

- monorepo layout
- Python control-plane package
- TypeScript runtime package
- shared schema/contract packages
- PostgreSQL + Alembic baseline
- RabbitMQ + Valkey local dev
- OpenTelemetry plumbing
- CI lint/type/test/migration checks

## Phase 1 — first vertical slice

Workspace → Project → Connection → Credential → Operation → Binding → PUBLIC runtime → Execution/Attempt → history → AuditEvent.

Exit criterion: real E2E test succeeds against actual PostgreSQL and encrypted credential storage.

## Phase 2 — Actions and idempotency

Durable IdempotencyRecord, WRITE semantics, INDETERMINATE handling, file/multipart coverage.

## Phase 3 — async reliability

Outbox, RabbitMQ, consumer dedupe, worker claims/fencing, scheduler, JobRun.

## Phase 4 — Webhooks and Notifications

Durable pre-ACK webhook ingestion, notification provider abstraction, expiry/dead-letter/provider callbacks.

## Phase 5 — Sync

Provider-neutral core, Framer adapter, Managed Collection path, dry-run, mappings, destructive-change guard, item-level history.

## Phase 6 — billing/entitlements/launch readiness

Usage reconciliation, quotas, controlled production, runbook verification, operational dashboards.
