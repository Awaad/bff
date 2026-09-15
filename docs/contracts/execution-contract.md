# Execution Contract

`Execution` is one logical invocation. `ExecutionAttempt` is one concrete processing attempt.

Automatic retries stay under one Execution. Manual replay creates a new Execution linked to the original.

## Execution states

PENDING, RUNNING, SUCCEEDED, REJECTED, FAILED, INDETERMINATE, CANCELLED, DEAD_LETTERED.

Pre-admission internet garbage need not create Execution rows. Customer-relevant rejection after capability resolution may create REJECTED with zero Attempts.

## Lineage

Execution records exact BindingRevision, OperationVersion, ConnectionRevision, and CredentialRevision.

Attempt records the exact CredentialSecretVersion used.

## Worker claims

Async claims use leases. Lease expiry permits recovery but does not prove the prior worker stopped.

A monotonic fencing/attempt token prevents stale workers from overwriting newer local state. It does not guarantee exactly-once remote effects.

## Retry

Retry is the intersection of OperationVersion semantics, normalized error, upstream idempotency safety, attempt limits, and platform caps.

Unsafe ambiguous writes become INDETERMINATE.

## Streaming/files

STREAM remains RUNNING while bytes flow. Terminal state is persisted when the stream ends/fails.

Binary/stream content is not stored directly in Execution rows.

Metadata and optional sanitized payload retention are separate.
