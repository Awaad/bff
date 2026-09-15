# ADR-0002: Immutable Versioned Runtime Configuration

**Status:** Accepted

## Context

Production execution must be reproducible, rollbackable, cacheable, and auditable. Mutable configuration such as base URLs, auth behavior, operation definitions, and exposure policy must not silently change historical or in-flight behavior.

## Decision

Use stable identity aggregates plus immutable revisions/versions:

- Connection -> ConnectionRevision
- Credential -> CredentialRevision + CredentialSecretVersion
- Operation -> OperationVersion
- Binding -> BindingRevision

BindingRevision is the immutable published composition. It pins exact OperationVersion, ConnectionRevision, Credential, and CredentialRevision. It intentionally does not pin CredentialSecretVersion so routine secret rotation does not require republishing.

Publication validates and compiles the complete composition into an immutable runtime artifact, then atomically switches the Binding active-revision pointer. Each accepted Execution remains pinned to one BindingRevision.

## Consequences

- Rollback is a pointer change to a previous valid revision.
- Immutable artifacts are safe to cache aggressively.
- Historical execution lineage is exact.
- More revision rows are created, but control-plane volume is expected to remain small.
- Draft/autosave state must be modeled separately from immutable published revisions.

## Alternatives Considered

- Mutable configuration rows: rejected because they destroy historical reproducibility.
- Pin CredentialSecretVersion in BindingRevision: rejected because ordinary secret rotation would require mass republishing.
