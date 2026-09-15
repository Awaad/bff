# ADR-0008: Provider-Neutral Synchronization Engine with Framer-First Adapters

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

Backend for Framer needs robust synchronization semantics: stable identity, incremental checkpoints, reconciliation, conflict handling, deletion safety, dry-runs, resumability, scheduling, idempotency, and item-level observability.

These concerns are not inherently Framer-specific. Hard-coding Framer concepts into the Sync core would either duplicate the hardest reliability logic for future providers or force a disruptive redesign later.

At the same time, the product is Framer-first and should not prematurely become a generic ETL/workflow builder.

## Decision

Build Sync as a provider-neutral, capability-driven reconciliation engine.

The generic core owns:

- SyncDefinition / SyncDraft / immutable SyncRevision
- stable source identity
- SyncMapping
- full/incremental modes
- durable checkpoints
- projection hashing
- conflict/missing policies
- mark-and-sweep reconciliation
- destructive-change guards
- SyncRun / SyncRunItem lifecycle
- resumability
- idempotency interaction
- scheduling integration
- observability

Provider behavior is implemented through typed SourceAdapter and TargetAdapter contracts with explicit capabilities.

Framer CMS is the first-class V1 adapter and receives specialized Plugin/Dashboard UX. Framer field IDs, Managed Collection semantics, user-editable fields, draft behavior, and publish/deploy remain inside the Framer adapter/configuration layer rather than generic core columns.

External API sides reuse INTERNAL Bindings and the canonical execution engine rather than introducing another HTTP stack.

The V1 product surface remains opinionated around Framer synchronization. Generic architecture is an implementation boundary, not a commitment to ship a generic ETL product.

## Consequences

### Positive

- Reconciliation logic is implemented once.
- Framer remains first-class without becoming hard-coded into core state.
- Future adapters can reuse identity, checkpoint, conflict, retry, and safety semantics.
- Capability differences are explicit instead of hidden behind false common guarantees.
- Existing execution, scheduling, idempotency, notification, and observability systems remain reusable.
- Product UX can stay Framer-focused.

### Negative

- Adapter interfaces and capability negotiation must exist earlier.
- Generic naming is slightly less convenient than Framer-specific columns.
- Tests must cover capability differences.
- Product scope discipline is required to avoid exposing generic pipeline concepts too early.

## Alternatives Considered

### Hard-code Framer CMS into Sync core

Rejected because the core reliability semantics are generic and would later require duplication or migration.

### Build a generic ETL/workflow product now

Rejected because it expands product scope and UX complexity without being needed for V1.

### Separate sync engines per provider

Rejected because it duplicates the hardest correctness logic and would produce inconsistent semantics.

## Invariants

- Sync core is provider-neutral.
- Framer is the first-class V1 specialization.
- Adapter capabilities are explicit and validated.
- Provider-specific identity/configuration does not leak into generic core columns.
- External API interactions reuse canonical Bindings/Executions where applicable.
- Generic architecture does not imply generic V1 product UX.
