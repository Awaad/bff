# Idempotency Contract

## Public Actions

Canonical uniqueness is scoped to stable Binding identity:

`(workspace_id, binding_id, key_hash)`

Same key + same canonical request hash reuses the original logical Execution/result.

Same key + different canonical request hash fails with `IDEMPOTENCY_KEY_REUSED`.

Publishing a new BindingRevision does not allow the same logical request to execute again.

## Failure semantics

FAILED does not automatically release the key for a fresh execution.

If a remote side effect may have occurred, the key remains bound to the original Execution and the result may be INDETERMINATE.

## Other domains

Use stronger domain identities where available:

- Webhook: provider event ID per stable endpoint
- Scheduler: `(job_definition_id, scheduled_for)`
- Notification: notification type + dedupe key
- Sync: SyncDefinition + source identity
- Usage: metric/event dedupe key

PostgreSQL is authoritative. Valkey may accelerate lookup but never defines correctness.
