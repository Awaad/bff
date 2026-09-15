# Jobs and Scheduler Contract

## Model

JobDefinition is stable schedule intent. JobRevision is immutable executable scheduling configuration. JobRun is one durable occurrence.

A Job targets exactly one Binding or one SyncDefinition.

## Occurrence identity

`(job_definition_id, scheduled_for)` is unique and authoritative.

`scheduled_for` is canonical intended UTC time, distinct from actual start time.

Schedules carry an explicit IANA timezone and deterministic DST semantics.

## HA scheduler

Multiple scheduler replicas are allowed. Correctness does not depend on a singleton leader.

Creating an occurrence and its OutboxEvent is atomic.

## Misfire

Supported policy classes:

- SKIP
- RUN_ONCE
- CATCH_UP_BOUNDED

Unbounded catch-up is forbidden.

## Overlap

- ALLOW
- SKIP_IF_RUNNING
- SERIALIZE

No implicit force-cancel/REPLACE for remote mutations.

## Pinning

JobRun pins the exact JobRevision and the relevant BindingRevision/SyncRevision selected at occurrence creation.

Later publications do not alter an existing occurrence.
