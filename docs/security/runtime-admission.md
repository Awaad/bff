# Runtime Admission — V2.1

## Required checks

The runtime resolves a public Binding identifier and validates mutable admission state before execution:

- Workspace ACTIVE
- Project ACTIVE
- Binding ACTIVE and PUBLIC
- active BindingRevision exists
- Connection ACTIVE
- Credential ACTIVE and usable
- Project may use Connection
- current Entitlements/quota/rate policy permit the invocation

After admission resolves a BindingRevision, the Execution remains pinned to it.

## Database role dependency

The runtime login inherits `bff_runtime_writer`.

That role can read the Workspace/Project/Binding/Connection/Credential/Entitlement state needed for admission and credential resolution, and can write Execution/Attempt/Idempotency/Usage/Outbox state.

Adding a new runtime admission dependency requires an ACL migration and permission test in the same change.
