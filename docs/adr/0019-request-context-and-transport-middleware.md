# ADR 0019: Request context and transport middleware

**Status:** Accepted  
**Date:** 2026-09-18

## Context

Authentication, audit records, OpenAPI contracts, outbox work and upcoming
transactional notifications need common request-level correlation without moving
business behavior into middleware.

## Decision

Every HTTP request receives a server-generated UUIDv7 `request_id`. An incoming
`X-Request-ID` is not trusted as the canonical identifier.

The response exposes:

```text
X-Request-ID: <uuidv7>
```

and Problem Details repeat the same value in `request_id` and `instance`.

The transport establishes a `RequestContext` containing:

```text
request_id
trace_id?
started_at
```

It is attached to request state. A `ContextVar` mirror exists only for
logging/telemetry convenience. Domain correctness must never depend on implicit
ContextVar state.

`RequestContextMiddleware` owns only cross-cutting transport concerns:

- generate the canonical request ID;
- capture an active OpenTelemetry trace ID when available;
- add `X-Request-ID` to responses;
- emit safe structured access logs;
- bind/reset logging context.

Middleware does not authenticate, authorize, own business transactions, implement
idempotency, send notifications, publish outbox events, or consume/log request
bodies.

Safe access logs contain only:

```text
request_id
trace_id
method
route template
status_code
duration_ms
```

Unmatched requests use `<unmatched>` instead of the raw requested path.

Durable application operations that need provenance receive request/actor context
explicitly. Future AuditEvent, OutboxEvent, Execution and Notification records may
copy request/trace correlation into durable metadata.
