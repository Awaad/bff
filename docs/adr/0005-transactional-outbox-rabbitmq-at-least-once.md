# ADR-0005: Transactional Outbox + RabbitMQ with At-Least-Once Delivery

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

The platform must reliably dispatch asynchronous work and domain events for Jobs, Sync, Webhooks, Notifications, execution workers, and other background workflows.

Writing authoritative state to PostgreSQL and publishing directly to a broker are two independent systems. Performing them sequentially creates a dual-write failure window:

- DB commits, broker publish fails -> work/event is lost;
- broker publish succeeds, DB transaction fails -> broker contains work that authoritative state does not reflect.

Using the broker itself as business truth would also weaken customer-visible history, idempotency, recovery, and operational debugging.

The system already requires at-least-once semantics and durable idempotency because remote side effects cannot generally provide exactly-once behavior.

## Decision

Use PostgreSQL transactional outbox as the durable bridge from authoritative domain state to RabbitMQ.

In the same transaction that creates/changes business state, insert an immutable typed/versioned OutboxEvent.

Independent dispatcher replicas claim OutboxEvents using database leases/row locking, publish to RabbitMQ, wait for publisher confirmation, then mark events published.

If RabbitMQ accepted a message but the dispatcher fails before recording `published_at`, the message may be published again. This is accepted.

Consumers are therefore explicitly at-least-once and must use domain-specific idempotency/deduplication.

RabbitMQ is durable work delivery, not business truth.

RabbitMQ DLQ state is transport state only; customer-visible failed/dead-lettered outcomes remain persisted in product/domain tables.

## Consequences

### Positive

- Eliminates the DB-commit / message-lost dual-write window.
- Business state remains authoritative in PostgreSQL.
- Broker outages do not lose work; pending OutboxEvents remain recoverable.
- Dispatcher can scale horizontally without singleton correctness assumptions.
- Duplicate delivery is explicit and handled through durable idempotency rather than hidden.
- Customer operations history survives broker cleanup/DLQ retention.
- Queue topology can evolve independently from business contracts.

### Negative

- Requires an OutboxEvent table and dispatcher service/process.
- Duplicate broker messages remain possible and must be handled correctly.
- Publish confirmation does not make end-to-end processing exactly once.
- Requires retention/purge strategy for successful OutboxEvents.
- Consumer retry and business retry semantics must remain clearly separated.

## Alternatives Considered

### Publish directly to RabbitMQ after committing business state

Rejected because process/broker failure after commit can permanently lose required work.

### Publish to RabbitMQ inside the DB transaction

Rejected because external network I/O cannot participate atomically in the PostgreSQL transaction and would create long/fragile transactions.

### Use RabbitMQ as the authoritative job/event store

Rejected because broker state is not an appropriate durable product/audit source of truth.

### Use Valkey/Redis as the durable queue

Rejected as the primary durable work-delivery mechanism. Valkey remains non-authoritative cache/coordination infrastructure.

### Claim exactly-once delivery

Rejected because broker redelivery, dispatcher ambiguity, worker crashes, and external side effects make exactly-once end-to-end execution an unsafe claim.

## Invariants

- Domain state and OutboxEvent are committed atomically.
- Messages use stable IDs and versioned typed contracts.
- Secrets and large payloads do not travel in queue/outbox messages.
- Dispatcher marks published only after broker confirmation.
- Consumers acknowledge only after their durable processing boundary.
- Duplicate messages are expected and harmless through idempotency.
- RabbitMQ DLQ state never replaces persisted product failure state.
