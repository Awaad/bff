# ADR-0009: Immutable Audit Ledger for Material Control-Plane and Privileged Actions

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

Backend for Framer has multiple product surfaces, tenant administrators, automation workers, and future platform-support/operator workflows.

Execution history, logs, traces, metrics, and domain events are insufficient as an accountability ledger because they have different retention, volume, semantics, and security characteristics.

The platform needs durable answers to:

- who changed a material resource,
- what changed,
- from which surface,
- whether privileged/support access was involved,
- whether the action succeeded,
- which request/trace/resource IDs correlate to the action.

At the same time, audit history must not become a second runtime log stream or a long-lived store of plaintext secrets and arbitrary customer payloads.

## Decision

Create an append-only `AuditEvent` ledger for material control-plane, security-sensitive, and privileged/operator actions.

AuditEvent:

- is tenant-scoped by Workspace except for explicit platform-scope events,
- records normalized actor identity,
- preserves original privileged actor and effective tenant context for support/impersonation,
- uses stable typed action keys,
- records affected resource identity,
- stores sanitized before/after/diff metadata where useful,
- stores request/surface/correlation identifiers,
- never stores plaintext credentials/tokens/secrets,
- is persisted transactionally with successful material mutations whenever practical,
- is append-only and corrected only through additional events,
- has retention independent from runtime execution/payload history.

Routine high-volume runtime activity remains in Execution/telemetry rather than AuditEvent.

A global per-row cryptographic hash chain is not required in V1. The design allows later signed archival or immutable export mechanisms if regulatory needs justify them.

## Consequences

### Positive

- Material administrative and security actions have durable accountability.
- Support/impersonation cannot hide the real privileged actor.
- Tenant audit exports can be generated from structured product data rather than application logs.
- Audit retention can be longer than execution payload retention without retaining secrets.
- Runtime tables remain focused on operational execution rather than governance history.
- Successful state changes and audit records can normally commit atomically.

### Negative

- Requires explicit audit policy/action registry across domains.
- Before/after snapshots need careful redaction.
- Long retention introduces privacy/storage responsibilities.
- Some cross-system actions cannot be represented by one atomic transaction and need staged outcome events.

## Alternatives Considered

### Use application logs as audit history

Rejected because logs are not structured product truth, may be sampled/rotated, mix tenants/runtime noise, and have weaker transactional guarantees.

### Audit every runtime operation

Rejected because it duplicates Execution history and creates unacceptable volume.

### Store complete resource snapshots including secrets

Rejected because long-lived audit history must not become a credential/PII exfiltration surface.

### Global cryptographic hash chain from V1

Rejected because it introduces write serialization and operational complexity without a current regulatory requirement.

## Invariants

- Tenant audit always retains Workspace attribution.
- Privileged support actions preserve original actor identity.
- Successful material mutations create AuditEvents transactionally where practical.
- Audit rows are append-only.
- Plaintext secrets never enter the audit ledger.
- Corrections are additive.
- Audit retention is independent from execution history.
