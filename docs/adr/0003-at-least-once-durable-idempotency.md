# ADR-0003: At-Least-Once Execution with Durable Idempotency

**Status:** Accepted

## Context

Queues, worker crashes, network ambiguity, client retries, provider webhooks, and distributed failover make duplicate delivery unavoidable. Exactly-once execution cannot be honestly guaranteed, especially for remote side effects.

## Decision

Adopt at-least-once processing semantics with durable, domain-appropriate idempotency.

- Public ACTION idempotency uses durable Postgres reservations scoped to stable Binding identity.
- Same key + same canonical request reuses the original logical Execution/result.
- Same key + different request is rejected.
- Postgres uniqueness is authoritative; Valkey may accelerate lookups only.
- One logical Execution may have multiple ExecutionAttempts.
- Leases/fencing reduce duplicate local processing but do not imply exactly-once remote side effects.
- Upstream idempotency support is explicit OperationVersion policy.
- Ambiguous unsafe remote outcomes are represented as INDETERMINATE rather than blindly retried.
- Domain-specific dedupe identities (webhook event IDs, scheduled occurrences, usage meter events, notifications) remain domain-specific when that yields stronger integrity.

## Consequences

- Duplicate transport delivery is safe when domain idempotency is correctly implemented.
- Some remote outcomes remain fundamentally ambiguous.
- Retention of idempotency/dedupe state must be longer than relevant retry windows.
- Customer billing can meter logical Executions rather than retry Attempts.

## Alternatives Considered

- Exactly-once claim: rejected as technically misleading.
- Valkey-only idempotency: rejected because it is non-authoritative and may lose state.
- Retry every timeout: rejected because unsafe mutations may already have committed upstream.
