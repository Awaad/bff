# Canonical Cross-Aggregate Invariants

**Status:** Baseline schema contract  
**Date:** 2026-09-13  
**Companion:** `aggregate-design.md`, `schema.sql`, `migration-policy.md`

This file is the canonical cross-domain integrity contract for the first implementation. Rules are classified as **DB** when the baseline schema enforces them directly, **TX** when they require transactional domain-service logic, and **APP** when they require application/runtime validation.

## 1. Tenant and identity boundary

1. **DB** Workspace is the tenant ownership boundary. Important tenant resources carry `workspace_id` explicitly.
2. **DB** Cross-workspace composite references are rejected wherever practical through `(workspace_id, id)` unique keys and composite foreign keys.
3. **APP/TX** `workspace_id` on owned resources is immutable in ordinary operation. Transfers are explicit workflows.
4. **DB** Primary IDs are UUIDs generated as UUIDv7 by application/shared ID infrastructure; the DB does not depend on a provider-specific UUIDv7 function.
5. **DB** Public runtime identifiers are separate from primary keys and have independent activation/revocation history.
6. **TX** An ACTIVE Workspace must retain at least one active OWNER membership. This multi-row invariant is enforced by the Workspace domain under row lock, not a simple CHECK.
7. **DB** At most one active Membership period exists per `(workspace_id, user_id)`.

## 2. Project and Framer linkage

1. **DB** Project belongs to one Workspace.
2. **DB** At most one active FramerProjectLink exists per Project.
3. **DB** One external Framer project may have at most one active Backend-for-Framer Project link globally.
4. **APP/TX** Project suspension/archive rejects new runtime admission but does not rewrite historical Executions/Runs.
5. **APP** Framer authorization lifecycle is independent from Project lifecycle.

## 3. Connection access and executable composition

1. **DB** Connection belongs to one Workspace and may be shared by Projects in that Workspace.
2. **DB** `SELECTED_PROJECTS` access is represented by `connection_project_access`; every referenced Project is in the same Workspace.
3. **APP** `WORKSPACE` access does not require explicit access rows; `SELECTED_PROJECTS` does.
4. **DB** ConnectionRevision, Credential, CredentialRevision, CredentialSecretVersion, Operation and OperationVersion cannot cross Connection/Workspace ownership.
5. **APP/TX** Connection, Credential and Operation lifecycle kill switches override cached immutable Binding configuration at runtime.
6. **APP** Native provider adapters cannot bypass central transport/security controls.

## 4. Credential and secret integrity

1. **DB** Credential is stable identity; CredentialRevision is immutable auth semantics; CredentialSecretVersion is immutable encrypted material.
2. **DB/TX** At most one current CredentialRevision pointer and at most one preferred active SecretVersion pointer are maintained on Credential.
3. **APP** BindingRevision pins Credential + CredentialRevision, never CredentialSecretVersion.
4. **APP** ExecutionAttempt records the exact CredentialSecretVersion used.
5. **APP** Plaintext secrets never enter PostgreSQL, RabbitMQ, Valkey, runtime history, logs, traces or audit.
6. **APP** Revoked/destroyed historical secret versions are never resurrected for replay.
7. **TX** Secret activation/rotation is concurrency-safe and external validation is performed outside long DB transactions.

## 5. Operation and Binding

1. **DB** Operation belongs to one Connection and Workspace; OperationVersion belongs to that Operation.
2. **DB** OperationVersion number is unique per Operation and persisted versions are immutable.
3. **DB** Binding belongs to one Project and Workspace.
4. **DB** Binding has independent `kind = QUERY|ACTION` and `exposure_mode = PUBLIC|INTERNAL` dimensions.
5. **DB** Only PUBLIC Bindings may have BindingPublicIdentifier rows; at most one identifier is active at a time.
6. **DB** BindingRevision pins one exact OperationVersion, ConnectionRevision, Credential and CredentialRevision from the same Connection/Workspace graph.
7. **APP** QUERY may not publish a WRITE OperationVersion.
8. **APP** Publication compiles/validates the full composition before atomically switching `binding.active_revision_id`.
9. **APP** Runtime caller input cannot select arbitrary Connection/Credential/host/privileged transport options.
10. **APP** Each admitted Execution resolves one BindingRevision once and remains pinned to it.

## 6. Execution and attempts

1. **DB** Execution is one logical invocation; ExecutionAttempt is one concrete attempt.
2. **DB** `(execution_id, attempt_number)` is unique.
3. **APP/TX** Automatic retry creates a new Attempt under the same Execution; manual replay creates a new Execution linked by `replay_of_execution_id`.
4. **APP/TX** Execution terminal states are not silently reopened.
5. **APP** `INDETERMINATE` is first-class when an unsafe remote side effect may have occurred but cannot be confirmed.
6. **APP/TX** Lease/fencing protects local state from stale workers but does not imply exactly-once remote side effects.
7. **APP** Pre-admission garbage/abuse need not create Execution rows; customer-relevant accepted/rejected invocation may.
8. **DB** Execution stores exact immutable runtime lineage for historical queryability.
9. **APP** Payload retention is separate from Execution metadata and binary/stream bodies are not stored inline as normal history.

## 7. Public Action idempotency

1. **DB** Public request identity is unique on `(workspace_id, binding_id, key_hash)`.
2. **APP** Same key + same canonical request hash returns/reuses the original logical Execution/result.
3. **APP** Same key + different request hash returns an idempotency conflict and never executes again.
4. **APP** Publishing a newer BindingRevision does not change the Execution associated with an existing key.
5. **APP** Internal idempotency does not make an unsafe upstream mutation retryable.
6. **APP** Idempotency retention exceeds the meaningful client retry/recovery horizon.

## 8. Jobs and scheduler

1. **DB** JobDefinition belongs to one Project/Workspace and points to one active immutable JobRevision.
2. **DB** JobRevision targets exactly one of `binding_id` or `sync_definition_id`.
3. **DB** `(job_definition_id, scheduled_for)` uniquely identifies one logical scheduled occurrence.
4. **TX** Scheduler replicas may race; DB uniqueness decides occurrence creation.
5. **TX** JobRun creation and its OutboxEvent occur in one transaction.
6. **APP** Misfire policy is explicit and catch-up is bounded.
7. **APP** Overlap policy is explicit; V1 does not force-cancel previous remote side effects.
8. **APP** Binding-target JobRun pins the active BindingRevision at occurrence creation.
9. **APP** Sync-target JobRun creates a SyncRun pinned to the then-current SyncRevision.
10. **APP** RabbitMQ state is never the source of truth for JobRun status.

## 9. Webhooks

1. **DB** WebhookEndpoint belongs to one Project/Workspace; WebhookEndpointRevision is immutable.
2. **DB** At most one active public webhook identifier exists per Endpoint.
3. **APP** Signature verification uses exact raw request bytes where required.
4. **APP** Invalid/untrusted ingress does not create normal WebhookDelivery rows.
5. **TX** Provider ACK is returned only after `WebhookDelivery + OutboxEvent` commit durably.
6. **DB** Provider event dedupe uses stable Endpoint identity, not EndpointRevision.
7. **APP** Same provider event ID with same payload hash is a duplicate; same event ID with a different hash is an anomaly.
8. **APP** Providers lacking event IDs receive best-effort dedupe only; this limitation is explicit.
9. **APP** Accepted WebhookDelivery pins the selected BindingRevision and later publishes cannot alter it.
10. **DB/APP** Duplicate broker delivery cannot create a second original Execution for the Delivery; manual replay is a new replay Execution.
11. **APP** Verification secrets are versioned encrypted inbound secrets, not outbound Credentials.

## 10. Provider-neutral Sync

1. **DB/APP** SyncDefinition is stable identity; SyncRevision is immutable configuration; SyncDraft is mutable authoring state.
2. **APP** Sync core is provider-neutral. Framer-specific collection/field/publish semantics live in adapter config/capabilities.
3. **APP** Every SyncRevision requires stable source identity; row/array position is not a valid normal identity.
4. **DB** `(sync_definition_id, source_identity_hash)` uniquely identifies a SyncMapping.
5. **DB** Target identity is unique within a SyncDefinition when the adapter declares exclusive identity semantics.
6. **APP** FULL/INCREMENTAL scan mode is independent from DRY_RUN/APPLY execution mode.
7. **APP** Incremental absence never means deletion.
8. **APP** Absence-based delete/soft-delete occurs only after a completed authoritative FULL scan.
9. **APP** Failed/partial FULL scan performs no absence sweep.
10. **APP** Large unexpected destructive deltas enter `REQUIRES_CONFIRMATION` before mutation.
11. **TX** Incremental checkpoint advances only after corresponding processing is durable.
12. **APP/TX** V1 allows at most one active SyncRun per SyncDefinition.
13. **APP** SyncRun pins the exact SyncRevision and relevant BindingRevision(s).
14. **APP** Item mutation follows the same upstream idempotency / `INDETERMINATE` rules as Actions.
15. **APP** Scheduled Sync reuses JobDefinition/JobRun; there is no second scheduler.
16. **APP** Sync success and target publish/deploy outcome are distinct.

## 11. Outbox and consumer dedupe

1. **TX** Business state and OutboxEvent are inserted in the same PostgreSQL transaction.
2. **APP/TX** Multiple dispatchers may claim rows with lease/locking semantics.
3. **APP** Publisher confirmation precedes `published_at` marking.
4. **APP** Publish-after-confirm DB failure may cause duplicate broker delivery; consumers must therefore be idempotent.
5. **APP** Queue envelopes are small, typed/versioned references and never contain plaintext credentials or arbitrary large payloads.
6. **APP** Consumer ACK occurs only after durable handling.
7. **DB** Generic `consumer_deduplication` is used only where a stronger domain-specific unique key is unavailable.
8. **APP** Broker DLQ is transport state; customer-visible terminal/dead-letter state lives in domain tables.

## 12. Notifications

1. **DB/APP** Notification is one logical message, NotificationDelivery one channel, DeliveryAttempt one provider attempt.
2. **DB** Logical creation dedupes on stable `(workspace_id, notification_type, dedupe_key)`.
3. **APP** Producer domains emit durable facts/outbox events and do not call provider SDKs directly.
4. **APP** Recipient destination and rendered content/template version are snapshotted for deterministic retries.
5. **APP** `expires_at` overrides retry/backoff; stale transactional messages are not delivered indefinitely.
6. **APP** Provider acceptance is not equivalent to confirmed delivery.
7. **APP** Blind cross-provider failover is forbidden when prior acceptance is indeterminate.
8. **APP** REQUIRED notification types override ordinary user channel preferences.
9. **APP** Customer notification data is separate from platform SRE alerting.

## 13. Usage, billing and entitlements

1. **APP** Billing says what was purchased; Entitlements say what is allowed; Usage says what was consumed.
2. **DB** Billing/Subscription belongs to Workspace; free Workspace may have no BillingAccount.
3. **APP** Runtime never branches on marketing plan names or provider subscription status directly.
4. **DB/APP** Entitlement project scope must belong to the same Workspace.
5. **DB** UsageEvent is append-only with a stable dedupe key per billable event.
6. **APP** Logical Execution billing normally meters one logical Execution, not each retry Attempt; byte/cost metrics may meter actual Attempts.
7. **APP** Valkey counters are enforcement acceleration, not accounting truth.

## 14. Audit

1. **DB/APP** AuditEvent is append-only accountability data, not current business state.
2. **APP** Material control-plane/security/operator actions are audited; routine high-volume runtime operations are not duplicated into audit.
3. **DB** TENANT-scope AuditEvent requires `workspace_id`.
4. **APP** Support/impersonation records the real privileged actor plus effective tenant context.
5. **APP** Successful material mutations write audit in the same transaction where practical.
6. **APP** Audit before/after/diff data is sanitized; plaintext secrets/tokens never enter the ledger.
7. **APP** Corrections are additive events rather than updates to historical rows.
8. **APP** Audit retention/export policy is independent from Execution payload retention.

## 15. Retention classes

Retention is intentionally independent by data class:

- immutable authoring revisions: long-lived with owning aggregate history;
- mappings/current control state: retained while resource exists plus archive policy;
- Execution/Run metadata: operational retention, potentially partitioned by time;
- payload bodies: shorter retention and separately purgeable;
- idempotency/dedupe identities: at least the meaningful retry horizon;
- AuditEvent: comparatively long-lived;
- secret ciphertext: may be destroyed while non-secret historical metadata remains.

Exact durations remain a product/legal/entitlement policy decision and are not frozen in the baseline schema.
