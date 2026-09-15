# Schema Migration Policy

**Status:** Baseline policy  
**Date:** 2026-09-13

## Goals

Schema evolution must preserve production availability, immutable historical lineage, tenant isolation, and rollback/recovery options. Migrations are treated as deployable production code and are reviewed with the application changes that depend on them.

## Tooling

- PostgreSQL is the authoritative relational store.
- Control-plane migrations are expected to use Alembic or an equivalent explicit migration framework.
- `schema.sql` is the canonical baseline/desired schema for a fresh database; it is **not** run wholesale against an existing production database.
- Every production schema change receives a numbered migration and a matching application compatibility plan.

## Expand / migrate / contract

Breaking changes use an expand-and-contract sequence:

1. **Expand:** add nullable columns/tables/indexes/new enum-like CHECK values without removing old behavior.
2. **Dual compatibility:** deploy code that can read old/new forms and writes the new form where safe.
3. **Backfill:** migrate data in bounded, resumable batches with progress/metrics.
4. **Validate:** add/validate constraints only after data satisfies them.
5. **Cut over:** switch readers/runtime to the new representation.
6. **Contract:** remove obsolete columns/constraints only in a later release after rollback windows expire.

Do not combine destructive contraction with the first application release that depends on the new shape.

## Lock and latency discipline

- Avoid table rewrites and long AccessExclusive locks on high-volume tables.
- Create large indexes with `CREATE INDEX CONCURRENTLY` in production migrations where PostgreSQL permits it.
- Add foreign keys/large CHECK constraints with `NOT VALID`, backfill/fix data, then `VALIDATE CONSTRAINT` where useful.
- Prefer nullable-add + backfill + set-not-null over adding a non-null column with expensive legacy behavior.
- Batch high-volume backfills by UUID/time key and make them restartable.
- Migration transactions must be deliberately scoped; operations that cannot run inside one transaction are split into dedicated revisions.

## Immutable revision tables

Rows in immutable/versioned tables are never rewritten simply to make new application code easier. Introduce a new schema/version representation or create new revisions while preserving historical semantics.

Examples include:

- ConnectionRevision
- CredentialRevision
- CredentialSecretVersion metadata
- OperationVersion
- BindingRevision
- JobRevision
- WebhookEndpointRevision
- SyncRevision
- ExecutionAttempt
- UsageEvent
- AuditEvent

If a historical row is factually wrong due to a bug, preserve forensic history and use an explicit corrective migration/event rather than silently changing externally meaningful semantics where possible.

## Tenant constraints

New tenant-owned relationships should include explicit `workspace_id` and use workspace-aware composite foreign keys where practical. A migration that introduces a new cross-domain FK must prove no cross-workspace rows exist before validating the constraint.

## Status / enum evolution

The baseline schema intentionally uses `TEXT + CHECK` rather than PostgreSQL ENUM for most lifecycle/status fields. This makes rolling evolution easier.

To add a new status:

1. expand the CHECK constraint to allow both old and new values;
2. deploy writers/readers that understand the new status;
3. migrate state if required;
4. only remove obsolete values in a later contract migration.

Never deploy code that writes a status rejected by the currently deployed DB constraint.

## Active revision pointers and cycles

Stable aggregates may point to an active/current immutable revision. These pointers are convenience/admission state, not historical truth.

Migrations must preserve:

- child revision -> stable parent FK;
- parent `active_revision_id` -> child revision FK;
- same-parent validation in domain service/constraints where SQL cannot express it simply.

Historical runtime rows continue to carry the exact revision IDs used.

## Partitioning

Execution, ExecutionAttempt, UsageEvent, JobRun, WebhookDelivery, SyncRun/SyncRunItem and AuditEvent are designed to support time-based partitioning as volume requires it.

Do not introduce partitioning purely for theoretical scale. When adopted:

- preserve globally unique UUIDv7 IDs;
- make retention/drop operations time-based;
- ensure unique/dedupe constraints remain enforceable (possibly through a non-partitioned reservation/dedupe table where PostgreSQL partition uniqueness would otherwise be insufficient);
- test ORM query plans and FK limitations before cutover.

## Outbox migrations

Outbox schema changes are backward compatible across dispatcher and consumer versions. Message envelopes are independently versioned. A database migration must not require all queued old-version messages to disappear before deployment.

## Secret data migrations

- Never decrypt/re-encrypt customer secret material casually in application migrations.
- KMS/wrapping-key rotation uses dedicated resumable operational tooling.
- Migration logs must never print ciphertext/plaintext secret fields.
- Destruction of old secret ciphertext is a separate audited lifecycle operation, not an incidental schema cleanup.

## Backfill idempotency

Backfills must be safe to rerun. Prefer deterministic derived values and `UPDATE ... WHERE new_column IS NULL`/version guards. For generated ledger/history rows, use explicit unique dedupe keys.

## Rollback policy

Application rollback should normally be possible after the Expand and Dual-compatibility phases. Destructive Contract migrations are intentionally delayed until application rollback no longer requires the old representation.

Data-changing migrations must document whether they are:

- fully reversible,
- application-reversible but data-lossy,
- irreversible.

Irreversible migrations require explicit review and backup/restore instructions.

## Migration review checklist

Every migration PR answers:

- What tables and row counts are affected?
- What lock level/time is expected?
- Does it rewrite a large table?
- Is it compatible with both old and new application versions?
- Is there a resumable backfill?
- Are tenant constraints preserved?
- Are immutable historical semantics preserved?
- Is any sensitive data touched?
- What is rollback/recovery?
- Does a runbook need updating?
- Which application role owns reads/writes for every new or changed table?
- Does `docs/security/database-roles.sql` need new explicit grants/revokes?
- Do migration-owner `ALTER DEFAULT PRIVILEGES` still apply to objects created by this migration?
- Do ACL integration tests prove control/runtime/worker/retention roles can do exactly the intended operations?

## Baseline rule

Before first production deployment, squash exploratory local migrations into a reviewed baseline if convenient. After production data exists, migration history is append-only: do not rewrite already-applied migration files.


## Baseline V2 pre-implementation rule

Baseline V2 supersedes V1 before production data exists.

The V1→V2 changes should be folded into the initial `0001` migration if implementation has not yet shipped persistent environments.

Do **not** create fake historical migration churn for a schema that was never deployed.

Once any shared/staging/production environment depends on `0001`, all subsequent changes become additive migrations.

Database role/ACL provisioning in `security/database-roles.sql` is part of environment bootstrap and must be tested alongside migrations.


## Database privilege migrations

Schema and ACL evolution are one deployment unit.

A migration introducing a new table must identify the owning service role, grant minimum required privileges, preserve write-once restrictions, verify default-privilege ownership, and include permission tests for an allowed and a denied role.

Runtime and retention do not inherit blanket future-table privileges; extensions are explicit.
