# ADR-0007: Durable Webhook Ingestion Before Provider ACK

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

Backend for Framer receives provider webhook events that may be retried, duplicated, signed over raw request bytes, time-sensitive, and capable of triggering remote side effects through the canonical Execution engine.

If the platform acknowledges a provider before durably recording the event, a crash can permanently lose work. If it performs business processing before acknowledging, provider timeouts can cause duplicate delivery and side-effect ambiguity. Provider retries and internal worker retries are separate reliability dimensions.

Webhook authentication also requires correct signature verification, replay protection, and dedupe semantics.

## Decision

Webhook ingestion follows this contract:

```text
resolve endpoint
→ enforce gross ingress limits
→ verify provider authenticity using raw request bytes where required
→ enforce replay/timestamp policy where supported
→ deduplicate by stable provider event identity where available
→ begin database transaction
   → insert WebhookDelivery
   → insert OutboxEvent(PROCESS_WEBHOOK)
→ commit
→ return provider success ACK
→ dispatch asynchronously through RabbitMQ
→ worker creates canonical Execution(source=WEBHOOK)
```

Provider success ACK therefore means **the platform has durably accepted responsibility for the event**, not that downstream processing has finished.

Invalid/untrusted ingress does not create normal WebhookDelivery product records.

Stable provider event IDs are the preferred dedupe key and are scoped to the stable WebhookEndpoint rather than its revision. Same event ID with a different payload hash is treated as an anomaly. Providers without stable event IDs receive explicitly best-effort dedupe.

WebhookEndpoint configuration is immutable/versioned through WebhookEndpointRevision. Accepted WebhookDelivery records pin the BindingRevision that was active at durable acceptance.

Webhook processing is asynchronous in V1. Synchronous arbitrary request/response functions are a distinct capability.

## Consequences

### Positive

- No acknowledged provider event is intentionally dependent on volatile process memory.
- Provider retries cannot create duplicate logical Deliveries when stable event IDs exist.
- Long-running business processing does not delay provider acknowledgement.
- Broker redelivery cannot create duplicate original Executions when domain uniqueness is enforced.
- Historical Deliveries remain tied to exact ingress and Binding configuration.
- Provider and internal retry semantics remain clearly separated.
- RabbitMQ remains transport rather than product truth.

### Negative

- Requires durable WebhookDelivery state and Outbox integration.
- Requires bounded raw-body handling for signature verification.
- Requires payload storage/reference lifecycle independent from Delivery metadata.
- Providers without stable event IDs cannot receive the same dedupe guarantees.
- Provider-specific ACK semantics and signature schemes require adapters.

## Alternatives Considered

### ACK before database commit

Rejected because a crash after ACK but before durable persistence can permanently lose the provider event.

### Perform downstream business work before ACK

Rejected because slow/failed processing causes provider retries and increases duplicate-side-effect risk.

### Store invalid signature attempts as normal WebhookDelivery rows

Rejected because untrusted internet traffic could cheaply flood customer product history and blur the trusted acceptance boundary.

### Deduplicate by EndpointRevision

Rejected because a provider retry after a configuration publish must still dedupe against the original logical event.

### Treat webhook ingress as a synchronous function endpoint

Rejected for V1 because webhook event ingestion and synchronous request/response execution have materially different latency and failure contracts.

## Invariants

- Success ACK is emitted only after WebhookDelivery and Outbox intent commit successfully.
- Verification precedes trusted Delivery creation.
- Provider event dedupe is authoritative in the database.
- Accepted Delivery pins the BindingRevision selected at acceptance time.
- Duplicate provider requests do not enqueue duplicate original work.
- Webhook business processing occurs asynchronously through the canonical Execution engine.
- Product-visible webhook state survives broker cleanup/DLQ behavior.
