# Runbook: Stuck or Duplicate Worker Claims

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger
Lease age exceeds threshold, the same Execution appears concurrently active, or stale workers attempt late finalization.

## Safety
Do not manually mark remote mutations failed merely because a lease expired. Lease expiry is not proof the old worker stopped.

## Diagnose
1. Inspect Execution/Attempt lease IDs and expirations.
2. Correlate worker traces.
3. Determine whether an upstream request may already have been sent.
4. Verify fencing/current-attempt state.

## Mitigate
Allow stale lease reclaim through the normal claim path. Prevent stale attempts from updating current state. If remote side effect is ambiguous and no upstream idempotency exists, resolve as INDETERMINATE rather than retrying blindly.

## Verify
Only the current fenced attempt can finalize local state; duplicate delivery remains harmless.
