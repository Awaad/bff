# Backend for Framer — Engineering Documentation

This directory is the engineering contract for Backend for Framer.

## Rules

1. Accepted ADRs are immutable; supersede rather than rewrite.
2. Documented does not mean implemented.
3. If code and docs disagree, fix one in the same PR.
4. Runbooks must carry a `Last verified` date after exercise.
5. Schema invariants are mandatory and must be enforced by PostgreSQL or by a named transactional domain service with tests.
6. Secrets and arbitrary customer payloads must never appear in docs except synthetic examples.

## Reading order

1. `00-context/product-scope.md`
2. `00-context/product-surfaces.md`
3. `architecture.md`
4. `schema/invariants.md`
5. `schema/schema.sql`
6. `contracts/`
7. `security/`
8. `adr/`
9. `handoff/current-state.md`
10. `runbooks/`

## Architectural summary

- Modular monorepo.
- Separate control-plane and execution-plane deployables from day one.
- Python/FastAPI control plane.
- TypeScript/Node canonical execution engine.
- PostgreSQL is authoritative durable state.
- RabbitMQ is durable at-least-once work delivery.
- Valkey/Redis is non-authoritative cache/rate-limit/coordination.
- Published runtime revisions are immutable and pinned.
- At-least-once execution + durable idempotency; never claim exactly-once.
- OpenTelemetry from the first executable version.
- Customer execution history, platform telemetry, and audit are separate concerns.
