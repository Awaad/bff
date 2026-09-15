# Runbook: Scheduler Lag / Missed Occurrences

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger

Oldest due JobDefinition exceeds scheduling SLO or expected JobRuns are absent.

## Safety

Do not manually create duplicate occurrences. Preserve `(job_definition_id, scheduled_for)` uniqueness.

## Diagnose

1. Check scheduler replicas and DB connectivity.
2. Compare current time with due indexes/`next_due_at` hints.
3. Check lease/claim contention.
4. Check Outbox backlog after JobRun creation.
5. Inspect DST/timezone/misfire policy for affected jobs.

## Recover

Resume scheduler capacity. Allow normal occurrence uniqueness to dedupe concurrent recovery. Apply configured misfire policy; do not invent unbounded catch-up.

## Verify

Expected JobRuns exist once, schedules advance correctly, and no duplicate logical occurrences were created.
