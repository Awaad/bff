# Backend for Framer

A Framer-first hosted backend for secure API calls, actions, jobs, webhooks, synchronization, and operational visibility.

> Status: repository, authentication, HTTP transport, developer bootstrap, and
> Workspace authorization are implemented. Project is the next Phase 1 domain.

## Why

Framer projects often need server-side behavior that cannot safely live in browser code: third-party API credentials, mutations, file transfers, background work, webhook ingestion, synchronization, and reliable operational history.

Backend for Framer provides that runtime while keeping secrets server-side and giving builders a Framer-native authoring experience.

## Architecture

- **Control plane:** Python / FastAPI
- **Execution plane:** TypeScript / Node
- **Database:** PostgreSQL — authoritative state
- **Durable work delivery:** RabbitMQ — at-least-once
- **Cache / rate limits / coordination:** Valkey/Redis — non-authoritative
- **Telemetry:** OpenTelemetry
- **Secret protection:** versioned envelope-encrypted credentials through a KMS abstraction
- **Frontend:** Web Dashboard + Framer Plugin

The repository is intended to be a modular monorepo with strong domain boundaries and separately deployable control-plane/runtime/worker entrypoints.

## Core principles

- immutable published revisions
- exact historical runtime lineage
- at-least-once execution + durable idempotency
- never claim exactly-once remote side effects
- public identifiers are separate from internal UUIDv7 PKs
- tenant-aware database constraints
- transactional outbox
- customer execution history separate from platform telemetry
- AuditEvent separate from both
- provider-neutral Sync core with Framer-first UX

## Documentation

Start here:

1. [`docs/README.md`](docs/README.md)
2. [`docs/00-context/product-scope.md`](docs/00-context/product-scope.md)
3. [`docs/architecture.md`](docs/architecture.md)
4. [`docs/schema/invariants.md`](docs/schema/invariants.md)
5. [`docs/schema/schema.sql`](docs/schema/schema.sql)
6. [`docs/handoff/build-sequence.md`](docs/handoff/build-sequence.md)

Schema Baseline V2 hardening review:

- [`docs/schema/review-2026-09-13-v2.md`](docs/schema/review-2026-09-13-v2.md)

## Repository layout

The implementation will converge toward:

```text
apps/
  control-api/
  runtime/
  dashboard/
  framer-plugin/

workers/
  execution/
  scheduler/
  outbox/
  webhook/
  notification/
  sync/

packages/
  execution-engine/
  contracts/
  provider-adapters/
  sync-adapters/

docs/
```

Exact package names may change during Phase 0 without changing the domain contracts.

## Local development

Copy the local template once, edit machine-specific values, then use the root
Makefile as the developer interface:

```bash
cp .env.example .env
make bootstrap
make api
```

Useful commands:

```bash
make help
make doctor
make db-sync
make auth-live
make test
make check
```

`make bootstrap` is non-destructive: it installs locked dependencies, starts local
infrastructure, runs real Alembic migrations, and reapplies the current database
application-role policy. It never deletes Docker volumes or stamps unapplied
migrations as complete.

See [`docs/development/local-development.md`](docs/development/local-development.md)
for the complete workflow and the stricter WorkOS environment checks.

## Database

`docs/schema/schema.sql` is the canonical pre-implementation PostgreSQL baseline.

Important companion files:

- `docs/schema/invariants.md`
- `docs/schema/migration-policy.md`
- `docs/security/database-roles.sql`

Do not implement from `schema.sql` alone.

## Testing expectations

Before broad production access, the project requires:

- domain invariant tests
- database constraint/adversarial tests
- cross-tenant tests
- idempotency/redelivery tests
- credential leakage/redaction tests
- scheduler failure tests
- webhook forgery/replay tests
- Sync deletion-guard tests
- real E2E vertical slices

## Security

Do not report security issues in a public issue tracker once the repository is public.

A dedicated security contact/process will be documented before public launch.

## License

Licensed under the Apache License 2.0. See [`LICENSE`](LICENSE).

## Current phase

Next implementation milestone:

```text
Workspace
→ Project
→ Connection
→ Credential
→ Operation
→ Binding publication
→ public runtime
→ Execution/Attempt
→ history
→ AuditEvent
```

Build it production-shaped and E2E-tested before broadening scope.
