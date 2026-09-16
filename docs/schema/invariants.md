# Canonical Cross-Aggregate Invariants

**Status:** Living canonical contract  
**Baseline:** V2.1 frozen 2026-09-13; additive evolution follows migration policy

Classification:

- **DB** — enforced directly by schema constraints/indexes.
- **DB-ACL** — enforced by PostgreSQL privileges from `security/database-roles.sql`; deployment must apply those roles.
- **TX** — enforced by a named transactional domain-service operation.
- **APP** — enforced by validation/runtime policy and covered by tests.

## 1. Tenant and identity

1. **DB** Workspace is the tenant boundary; important tenant resources carry `workspace_id`.
2. **DB** Tenant-aware composite FKs prevent cross-workspace references wherever practical.
3. **TX** Owned-resource `workspace_id` is immutable in ordinary operation; transfers use explicit workflows.
4. **APP** Primary UUIDs are application-generated UUIDv7. PostgreSQL validates UUID type only; it does not prove UUIDv7 generation.
5. **DB** Public Binding/Webhook identifiers are separate from internal PKs and have independent activation/revocation history.
6. **TX** ACTIVE Workspace retains at least one active OWNER.
7. **DB** At most one active Membership period exists per `(workspace_id, user_id)`.
8. **DB** Every UserAuthIdentity references exactly one User.
9. **DB** OIDC authentication identity is globally unique on exact `(issuer, subject)`.
10. **DB-ACL** Ordinary application roles cannot mutate UserAuthIdentity `user_id`, `issuer`, or `subject`; control may change lifecycle state only.
11. **APP** Email is profile/contact data and is never the key used to resolve an existing authenticated identity.
12. **APP/TX** Matching email addresses never auto-merge Users or external identities; linking or merge requires an explicit authenticated workflow.
13. **APP** Framer client user/project context is not accepted as server-verifiable BFF authentication or project-ownership proof by itself.

## 2. Project and Framer linking

1. **DB** Project belongs to one Workspace.
2. **DB** At most one ACTIVE FramerProjectLink exists per Project.
3. **DB** One verified ACTIVE external Framer project ID may be linked only once globally.
4. **APP/TX** A FramerProjectLink cannot become ACTIVE until backend verification proves the supplied Framer authorization/session can access the exact claimed Framer project.
5. **DB** ACTIVE FramerProjectLink requires verification metadata.
6. **APP/TX** Project suspension/archive rejects new work without rewriting history.

## 3. Immutable revision model and drafts

1. **DB** Revision/version rows belong to their stable parent and have unique revision/version numbers.
2. **DB-ACL** Published ConnectionRevision, CredentialRevision, OperationVersion, BindingRevision, SyncRevision, JobRevision, WebhookEndpointRevision, UsageEvent, and AuditEvent are write-once under application roles. CredentialSecretVersion secret material is immutable; only lifecycle/destruction columns are updateable.
3. **DB** Persistent mutable authoring state is separate: ConnectionDraft, OperationDraft, BindingDraft, SyncDraft, JobDraft, WebhookEndpointDraft. Connection, Operation, Binding, JobDefinition, SyncDefinition, and WebhookEndpoint may exist in DRAFT state before first publication.
4. **APP/TX** Publication validates/compiles draft state into a new immutable revision and atomically advances the parent's active/current pointer.

## 4. Connection/Credential/Operation composition

1. **DB** Connection belongs to one Workspace.
2. **DB** Selected-project Connection access cannot cross Workspace.
3. **DB** ConnectionRevision, Credential, CredentialRevision, SecretVersion, Operation, and OperationVersion cannot cross their parent Connection/Workspace.
4. **APP/TX** Connection/Credential/Operation lifecycle kill switches override cached immutable artifacts.
5. **APP** Provider adapters cannot bypass central network/security controls.
6. **DB/APP** `auth_scheme = NONE` is the first-class unauthenticated Credential form; it has empty auth configuration and no CredentialSecretVersion.

## 5. Binding

1. **DB** Binding belongs to one Project/Workspace.
2. **DB/DB-ACL** Binding has independent `kind = QUERY|ACTION` and `exposure_mode = PUBLIC|INTERNAL`; both are stable identity attributes and application roles cannot mutate them after creation.
3. **DB** BindingPublicIdentifier can reference only a PUBLIC Binding.
4. **DB** At most one active public identifier exists per Binding.
5. **DB** BindingRevision pins exact OperationVersion, ConnectionRevision, Credential, and CredentialRevision from one Connection graph.
6. **APP** QUERY publication cannot target a WRITE OperationVersion.
7. **APP/TX** Publication validates Project→Connection access, contracts, policies, and compiler compatibility.
8. **APP** Runtime callers cannot select arbitrary Connection/Credential/host/privileged transport fields.
9. **APP** Changing QUERY/ACTION kind or PUBLIC/INTERNAL exposure creates a new Binding identity rather than mutating an existing Binding.

## 6. Execution lineage

1. **DB** Every Execution has explicit `lineage_mode = BINDING|DIRECT`.
2. **DB** BINDING lineage requires both Binding and BindingRevision; DIRECT lineage requires both to be NULL.
3. **DB** Every Execution always pins exact ConnectionRevision, OperationVersion, Credential, and CredentialRevision.
4. **DB** BINDING lineage has one composite FK proving that all recorded revision IDs are the exact composition of the cited BindingRevision and Project.
5. **DB** DIRECT lineage independently proves Connection/Operation/Credential all belong to the same Connection.
6. **DB** Execution attribution to Binding is Project-aware, not merely Workspace-aware.
7. **DB** `public_execution_ref` is unique and separate from UUIDv7 PK.
8. **DB** `(execution_id, attempt_number)` is unique.
9. **DB-ACL** ExecutionAttempt identity/lineage fields are non-updatable by runtime/worker roles; only lifecycle/result columns are granted UPDATE.
10. **TX/APP** Automatic retry creates a new Attempt under the same Execution; manual replay creates a new Execution.
11. **APP** INDETERMINATE is first-class for ambiguous unsafe remote side effects.

## 7. Idempotency

1. **DB** Public Action identity is unique on `(workspace_id, binding_id, key_hash)`.
2. **APP** Same key + same canonical request reuses the original Execution/result.
3. **APP** Same key + different request is rejected.
4. **APP** Publishing a new BindingRevision does not alter an existing idempotency record's Execution.
5. **APP** Internal idempotency does not make unsafe upstream retries safe.
6. **DB** `expires_at` is indexed for retention sweeps.

## 8. Jobs

1. **DB** JobRevision targets exactly one Binding or SyncDefinition.
2. **DB** JobRun target lineage is pair-complete and Project-aware.
3. **DB** `(job_definition_id, scheduled_for)` uniquely identifies an occurrence.
4. **TX** Scheduler replicas race safely; DB uniqueness decides occurrence creation.
5. **TX** JobRun + OutboxEvent commit together.
6. **APP** Misfire/DST/overlap semantics are explicit and bounded.

## 9. Webhooks

1. **DB** Endpoint belongs to one Project/Workspace and revisions are immutable under DB-ACL.
2. **DB** At most one active public identifier exists per Endpoint.
3. **APP** Signature verification uses raw bytes and replay-window policy.
4. **TX** Provider ACK occurs only after verified Delivery + Outbox commit.
5. **DB** Provider event dedupe is scoped to stable Endpoint.
6. **APP** Same provider event ID with different payload hash is an anomaly.
7. **DB** Accepted Delivery pins exact BindingRevision.
8. **DB** `payload_ref` may become NULL only when `payload_purged_at` records deliberate purge.
9. **APP** Invalid ingress does not create ordinary Delivery rows.

## 10. Sync

1. **DB** SyncDefinition/SyncRevision/SyncDraft are separate stable/published/draft state.
2. **APP** Core is provider-neutral; provider capabilities remain adapter-specific.
3. **DB** `(sync_definition_id, source_identity_hash)` is unique.
4. **APP** Target identity uniqueness is enforced only for adapters declaring exclusive identity.
5. **DB** Source/target Binding lineage on SyncRun is both-null or both-nonnull and Project-aware.
6. **APP** Incremental absence never implies deletion.
7. **APP** Absence sweep requires a completed authoritative FULL scan.
8. **APP** Destructive deltas can enter REQUIRES_CONFIRMATION.
9. **DB** At most one active SyncRun exists per SyncDefinition.

## 11. Outbox / consumer dedupe

1. **DB** OutboxEvent is durable database state.
2. **TX/APP** Multiple dispatchers claim safely; broker confirm precedes publication mark.
3. **APP** Duplicate publication is expected after publish-confirm ambiguity; consumers are idempotent.
4. **APP** Queue envelopes contain references, not secrets/large arbitrary payloads.
5. **DB** `processed_at` and `published_at` retention paths are indexed.

## 12. Notifications

1. **DB** Logical Notification dedupes on `(workspace_id, notification_type, dedupe_key)`.
2. **APP** V1 persisted channels are EMAIL and IN_APP only; SMS is future capability.
3. **APP** Producer domains emit durable events rather than calling providers.
4. **APP** Recipient/template/rendered content is snapshotted for retries.
5. **APP** Expiration overrides retry.
6. **DB** `expires_at` has a sweep-oriented partial index.
7. **APP** Provider accepted != delivered.

## 13. Usage/Billing/Entitlements

1. **APP** Billing, Entitlements, and Usage are separate semantics.
2. **DB** Billing belongs to Workspace.
3. **DB-ACL** UsageEvent is append-only under application roles.
4. **DB** UsageEvent has a stable dedupe key per metric/workspace.
5. **APP** Logical Execution billing normally meters one Execution, not retries.
6. **APP** Valkey counters are not accounting truth.

## 14. Audit

1. **DB** TENANT-scope AuditEvent requires Workspace.
2. **DB-ACL** AuditEvent is append-only under application roles.
3. **APP** Material administrative/security/operator actions are audited.
4. **APP** Support/impersonation retains real privileged actor and effective context.
5. **TX** Successful material mutation writes AuditEvent in the same transaction where practical.
6. **APP** Audit payload is sanitized and never contains plaintext secrets.
7. **APP** Corrections are additive.

## 15. Identifier semantics

1. **APP** UUIDv7 PKs are globally unique and practically unguessable but time-ordered; they may reveal approximate creation time.
2. **DB** Public runtime identifiers and `public_execution_ref` are separate identifiers.
3. **APP** Public capability security never depends on secrecy of an internal UUID.


## 16. Database application roles

1. **DB-ACL** Public runtime can read all state required by runtime admission and credential resolution.
2. **DB-ACL** Public runtime can write Executions, Attempts, IdempotencyRecords, UsageEvents, and OutboxEvents required by runtime processing.
3. **DB-ACL** Retention/purge uses the separate `bff_retention` role; ordinary runtime/control roles do not receive blanket DELETE.
4. **DB-ACL** Future tables receive default SELECT only for control/worker roles when created by the configured migration owner. Runtime/retention privileges remain explicit per migration.
5. **TX/APP** Every migration adding a table or changing ownership responsibilities updates and tests ACLs.
