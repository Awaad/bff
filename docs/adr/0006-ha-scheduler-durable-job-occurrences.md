# ADR-0006: HA Scheduler with Durable, Deduplicated Job Occurrences

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

The product core includes scheduled Jobs. Scheduling must remain correct across scheduler restarts, multiple scheduler replicas, broker outages, clock/timezone behavior, and missed schedule windows.

A singleton in-memory scheduler would create a fragile availability boundary. Enqueuing a job directly without first persisting the occurrence can lose scheduled work. Conversely, multiple scheduler replicas can create duplicate logical runs unless occurrence identity is protected durably.

Historical runs must also remain attributable to the exact schedule and executable Binding configuration used at the time.

## Decision

Represent Jobs as:

- `JobDefinition` — stable identity/lifecycle.
- `JobRevision` — immutable schedule, target, overlap and misfire configuration.
- `JobRun` — one durable logical scheduled occurrence.

Persist each occurrence with unique identity:

`(job_definition_id, scheduled_for)`

where `scheduled_for` is the canonical intended UTC occurrence time.

Run multiple scheduler replicas safely. Scheduler replicas query/claim due definitions using PostgreSQL locking/lease semantics and rely on the unique occurrence constraint to resolve races.

Creating JobRun and its dispatch OutboxEvent occurs in the same PostgreSQL transaction.

`next_due_at` is an optimization only; schedule definition + persisted JobRuns are authoritative.

Schedules use explicit IANA timezone semantics.

V1 supports explicit bounded misfire policies (`SKIP`, `RUN_ONCE`, `CATCH_UP_BOUNDED`) and overlap policies (`ALLOW`, `SKIP_IF_RUNNING`, `SERIALIZE`). Unbounded catch-up and unsafe implicit replacement/cancellation are forbidden.

At occurrence creation, JobRun pins the exact active BindingRevision it will execute. Later Binding publication does not alter the run.

## Consequences

### Positive

- Scheduler can be horizontally redundant without leader/singleton dependency.
- Duplicate logical scheduled occurrences are prevented by the database.
- Broker outages do not lose occurrences because dispatch intent is persisted through Outbox.
- Historical JobRuns are reproducible against immutable JobRevision and BindingRevision.
- Missed-run and overlap behavior is explicit rather than accidental.
- Timezone/DST semantics can be tested deterministically.

### Negative

- Adds JobRevision and durable JobRun state.
- Scheduler requires careful due-time calculation and database locking.
- Misfire/overlap policies add product complexity.
- Very frequent schedules can create significant JobRun history and require retention controls.

## Alternatives Considered

### Singleton scheduler process

Rejected because scheduler availability/correctness would depend on one process and failover mechanism.

### Let RabbitMQ scheduled/delayed messages be schedule truth

Rejected because broker state should not be the authoritative record of customer schedule intent/occurrences.

### Create a new run whenever any scheduler observes a due job

Rejected because multiple replicas/restarts can produce duplicate logical occurrences.

### Unbounded catch-up after downtime

Rejected because long outages could create dangerous execution storms and remote side effects.

## Invariants

- JobRevision is immutable.
- One `(job_definition_id, scheduled_for)` maps to one logical JobRun.
- Multiple scheduler replicas are safe.
- JobRun + OutboxEvent are created atomically.
- JobRun pins exact JobRevision and BindingRevision.
- Later config publication does not mutate an existing occurrence.
- Broker delivery remains at-least-once; execution retries happen as ExecutionAttempts.
