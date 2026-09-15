# Runtime Admission

Immutable BindingRevision describes what to execute. Mutable admission state decides whether it is currently permitted.

Required semantic checks:

- Workspace ACTIVE
- Project ACTIVE
- Binding ACTIVE
- correct PUBLIC/INTERNAL exposure
- active BindingRevision exists
- Connection ACTIVE
- Credential ACTIVE and usable
- Project currently allowed to use Connection
- Entitlements permit
- quota/rate policy permits

Mutable state overrides historically valid immutable config.

After admission resolves a BindingRevision, the Execution remains pinned to it.

Disable normally blocks new admissions and does not blindly cancel already-sent mutations.

Immutable compiled artifacts may be cached aggressively; mutable admission state needs bounded freshness. Cache is never authoritative.
