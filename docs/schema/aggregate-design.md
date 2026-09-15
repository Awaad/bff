# Aggregate Design

**Status:** Draft / Living specification  
**Purpose:** Define aggregate ownership, cardinality, lifecycle, invariants, and scalability characteristics before producing the canonical SQL schema.

Aggregate review is complete; this document is now the retained design rationale for the baseline schema.

> **Schema-freeze note (2026-09-13):** Aggregate review is complete. Later accepted decisions supersede earlier exploratory wording. The canonical cross-aggregate rules now live in `invariants.md`; `schema.sql` is the baseline PostgreSQL model. This document remains design rationale, not the sole schema contract.

After all aggregates have been reviewed, it will produce:

- `docs/schema/invariants.md`
- `docs/schema/schema.sql`
- `docs/schema/migration-policy.md`
- architecture ADRs for decisions crossing multiple domains

---

# 0. General Data-Model Rules

## 0.1 Tenant Ownership

`Workspace` is the tenant ownership boundary.

Every important tenant-owned resource explicitly carries `workspace_id`, even where ownership could be derived indirectly.

Critical relationships should use workspace-aware foreign keys where practical, e.g. `(workspace_id, connection_id) -> connections(workspace_id, id)`.

## 0.2 Aggregate Boundaries

Workspace is the tenant root, not one giant transactional aggregate. Project, Connection, Credential, Operation, Billing, Execution, etc. remain independently owned aggregates/domains.

Cross-domain mutation occurs through domain services/contracts rather than direct repository access.

## 0.3 Configuration vs Runtime State

### Control State
- Workspace
- Project
- Connection
- Credential
- Operation
- Binding
- SyncDefinition
- JobDefinition
- WebhookEndpoint

### Durable Runtime State
- Execution
- ExecutionAttempt
- SyncRun
- JobRun
- WebhookDelivery
- IdempotencyRecord

### Reliability State
- OutboxEvent
- consumer deduplication/inbox where required
- leases and claims

### Audit / Accounting
- AuditEvent
- UsageEvent
- UsageBucket
- Billing records

High-volume state must remain separable from low-churn control-plane state.

## 0.4 Immutability

Revision/history records should generally be immutable or append-oriented, including ConnectionRevision, CredentialRevision, CredentialSecretVersion, OperationVersion, BindingRevision, ExecutionAttempt, UsageEvent, and AuditEvent.

## 0.5 Identifiers

Primary resource IDs should use globally unique, non-enumerable IDs, currently expected to be UUIDv7. Public runtime identifiers should remain independent from database primary keys and revocable where appropriate.

---

# 1. Workspace / Membership

## Purpose

Workspace is the tenant, commercial ownership, and collaboration boundary. Users belong to Workspaces through Memberships. Resources belong to Workspaces rather than directly to Users.

## Ownership and Cardinality

- A User may belong to many Workspaces.
- A Workspace may contain many Users.
- A Membership belongs to exactly one User and one Workspace.
- A User may have at most one active Membership period per Workspace.
- A Workspace may have multiple active OWNER memberships.

## Roles

Initial roles: `OWNER`, `ADMIN`, `BUILDER`, `VIEWER`.

Roles are permission bundles; authorization should reason in permissions rather than scattered role-name conditionals.

## Membership Lifecycle

Membership rows represent membership periods. Removed memberships remain historical. A later rejoin creates another Membership period. Pending invitations are separate from Memberships.

## WorkspaceInvitation

Contains workspace, normalized email, intended role, inviter, hashed invitation token, expiration, and accepted/revoked lifecycle. Raw invitation tokens are never stored.

## Workspace Lifecycle

Expected states: `ACTIVE`, `SUSPENDED`, `ARCHIVED`. Possible later: `PENDING_DELETION`.

Billing delinquency does not directly mutate Workspace status.

## Owner Invariant

Every active Workspace must have at least one active OWNER. Owner removal/demotion must transactionally ensure another active owner remains.

## Tenant Integrity

Important Workspace-owned resources carry `workspace_id`. Cross-workspace relationships are forbidden. Critical references should use composite workspace-aware FKs.

## Frozen Invariants

1. Workspace is the tenant ownership boundary.
2. Resources belong to Workspaces rather than Users.
3. Users may belong to multiple Workspaces.
4. Every active Workspace has at least one active OWNER.
5. Multiple owners are allowed.
6. At most one active Membership period exists per User/Workspace.
7. Invitations are separate from Memberships.
8. Invitation tokens are stored only as hashes.
9. Important tenant-owned resources explicitly carry `workspace_id`.
10. Cross-workspace relationships are forbidden.
11. Commercial plan does not live on Workspace.
12. Billing state and Workspace lifecycle are separate.
13. Personal use is represented by a normal Workspace.
14. Workspace deletion is a workflow, not an immediate cascade.
15. Workspace ownership IDs are not casually mutable.
16. Authorization operates on permissions; roles bundle permissions.

---

# 2. Project

## Purpose

Project is our internal representation of one frontend project operated through Backend for Framer. The product remains Framer-first while Project stays internally platform-neutral.

## Ownership

Project belongs to exactly one Workspace. `Project.workspace_id` is immutable during normal operation.

## Framer Relationship

A Project has zero or one active Framer project link. One external Framer project may have at most one active Backend-for-Framer Project link globally. Historical links are retained.

## Lifecycle and Admission

Expected Project states: `ACTIVE`, `SUSPENDED`, `ARCHIVED`; possible later `PENDING_DELETION`.

Runtime admission conceptually requires `Workspace active AND Project active AND Binding active AND Entitlement permits`.

Project does not contain `plan`, `is_pro`, or `is_production`; capability is resolved through Entitlements/profile assignment.

## Connection Access

Connections are Workspace-owned. Projects may receive access according to Connection access policy.

## Transfer

Changing `Project.workspace_id` directly is forbidden. Project transfer is an explicit workflow resolving all dependent resources.

## Frozen Invariants

1. Project belongs to exactly one Workspace.
2. Workspace ownership is not ordinarily mutable.
3. Project identity is ours, not Framer's.
4. Project may exist without a Framer link.
5. Project has at most one active Framer project link.
6. One Framer project has at most one active Backend Project link.
7. Link history is retained.
8. Project state and Framer-link state are independent.
9. Pricing/plan is not stored directly on Project.
10. Project is a valid entitlement and usage scope.
11. Project does not own Connections.
12. Project status independently gates runtime.
13. Runtime identity comes from Binding rather than Project primary ID.
14. Historical runtime data survives archive/disconnection.
15. Cross-Workspace transfer requires a dedicated workflow.

---

# 3. Billing / Entitlements / Usage

Billing answers what the customer purchased. Entitlements answers what the Workspace/Project may do. Usage answers what it consumed. They are separate domains.

## 3.1 Billing

Billing belongs to Workspace. A free Workspace may have no BillingAccount. A Workspace has at most one primary active recurring platform Subscription initially.

Provider identifiers are adapter metadata. Marketing package names are not runtime/domain conditions.

Subscription state does not directly gate runtime. Billing changes flow through policy into Entitlements. Payment-provider outage must not take customer sites offline.

### Billing Invariants

1. Billing belongs to Workspace, not User.
2. Free Workspaces need no BillingAccount.
3. Payment-provider identity is adapter metadata.
4. Marketing package names never appear in unrelated domain logic.
5. Billing status does not directly gate runtime.
6. Historical subscriptions are retained.
7. Provider webhooks are idempotently processed.
8. Subscription changes produce Entitlement changes through domain logic.

## 3.2 Entitlements

Entitlements are Workspace- or Project-scoped using `workspace_id` plus nullable `project_id` rather than a polymorphic subject FK.

Keys come from a typed application registry and define scope, value type, resolution rule, and enforcement type.

Expected grant sources: `SUBSCRIPTION`, `ADDON`, `FOUNDING_ACCESS`, `PROMOTION`, `MANUAL`, `ENTERPRISE_CONTRACT`.

Project capability profiles are entitlement bundles, not billing plans. Production project assignments consume Workspace capacity transactionally.

Metered execution allowance is generally Workspace-shared while usage remains attributable per Project.

Runtime combines static BindingRevision policy, current entitlements, and quota state. Volatile entitlement state is not embedded inside immutable BindingRevision.

Enforcement classes include `HARD`, `THROTTLE`, `SOFT/OVERAGE`, and `LIFECYCLE`.

### Entitlement Invariants

1. Entitlements may be Workspace- or Project-scoped.
2. Project grants must belong to the same Workspace.
3. Keys are defined in a typed registry.
4. Every key defines value type, resolution, and enforcement behavior.
5. Founding/manual/promotional access uses the same grant mechanism as paid access.
6. Runtime never checks marketing plan names.
7. Production Project capability consumes Workspace capacity.
8. Capacity assignment is transactionally protected.
9. Runtime uses locally available entitlement state.
10. Entitlement changes are auditable.
11. Usage allowances do not live inside BindingRevision.

## 3.3 Usage

Usage is durable metering/accounting state, separate from execution logs and fast quota counters.

UsageEvent is append-only and contains workspace, optional project, metric, quantity, source, dedupe identity, and occurrence time.

Every billable event has a stable dedupe identity. At-least-once infrastructure may not cause double billing. Corrections are compensating ledger entries.

UsageBucket aggregates raw usage for dashboard/billing queries. Valkey may maintain fast enforcement counters but is not accounting truth.

UsageEvent is expected to support time partitioning.

### Usage Invariants

1. Usage accounting is append-only.
2. Every billable event has a stable dedupe identity.
3. At-least-once processing must not double-charge.
4. Workspace is always recorded.
5. Project is recorded whenever attribution exists.
6. Raw events and aggregate buckets are separate.
7. Postgres is durable accounting truth.
8. Valkey provides enforcement acceleration only.
9. Corrections use compensating entries.
10. Shared Workspace allowance still supports Project reporting.
11. Enforcement is entitlement-specific.
12. Billing does not scan raw Execution history synchronously.
13. Usage state is partitionable.

---

# 4. Connection / ConnectionRevision

## Purpose

Connection represents a logical external system/account/environment boundary. It is not an API endpoint and not an executable operation.

Examples: `Acme HubSpot Production`, `Client A Internal API`, `Supabase Production`.

Operations define what can be done. Credentials define how execution authenticates.

## Ownership and Cardinality

Connection belongs to exactly one Workspace and is Workspace-owned rather than Project-owned.

- Workspace `1 -> N Connection`
- Connection `1 -> N ConnectionRevision`
- Connection `1 -> N Credential`
- Connection `1 -> N Operation`

Connection may be shared across Projects where policy permits.

## Revision Model

Connection executable/provider configuration is represented by immutable ConnectionRevision records. Changing base URL/destination/configuration creates a new revision rather than mutating historical executable meaning.

Published BindingRevision resolves a concrete ConnectionRevision rather than dynamically following the latest Connection configuration.

## Lifecycle

Expected: `ACTIVE`, `DISABLED`, `ARCHIVED`.

`DISABLED` is a mutable global kill switch. Health is separate derived operational state.

## Provider Model

Connection supports both generic HTTP and provider-native integrations through a typed provider registry. Provider-specific configuration is schema-validated.

Native provider adapters may not bypass the central outbound HTTP transport/security policy.

## Project Access

Connections support `WORKSPACE` or `SELECTED_PROJECTS` access. Revoking Project access must affect runtime admission even if stale immutable Binding configuration exists.

## Credentials and Operations

Credentials are separate entities. Operation belongs to exactly one Connection. Runtime callers cannot dynamically choose arbitrary Connection, destination, or Credential values.

## Frozen Invariants

1. Connection is an external-system/account/environment boundary, not an endpoint.
2. Connection belongs to exactly one Workspace.
3. Connection is Workspace-owned rather than Project-owned.
4. Connection may be shared across Projects according to explicit access policy.
5. Connection executable/provider configuration is revisioned.
6. ConnectionRevision is immutable.
7. Destination/base URL changes create a new ConnectionRevision.
8. Published runtime configuration resolves a concrete ConnectionRevision.
9. Connection lifecycle includes an explicit mutable kill switch.
10. Health state is separate from lifecycle state.
11. Generic and native providers use one Connection model.
12. Provider-specific config is schema-validated through a provider registry.
13. Native adapters may not bypass central outbound transport/security policy.
14. Credentials are separate entities and a Connection may have multiple Credentials.
15. Operation belongs to exactly one Connection.
16. Runtime callers cannot choose arbitrary Connection/destination/Credential values.
17. Project Connection-access revocation must affect runtime admission.
18. Connection `workspace_id` is not ordinarily mutable.
19. Historical revisions survive archive.
20. Connection configuration revision and Credential secret rotation remain separate concepts.

---

# 5. Credential / CredentialRevision / CredentialSecretVersion

## Purpose

Credential is a stable authentication identity for one Connection. CredentialRevision describes how authentication is applied. CredentialSecretVersion contains immutable encrypted secret material.

Runtime resolves the currently usable SecretVersion at the last responsible moment.

## Ownership and Cardinality

Credential belongs to exactly one Workspace and one Connection.

- Connection `1 -> N Credential`
- Credential `1 -> N CredentialRevision`
- Credential `1 -> N CredentialSecretVersion`
- Credential has one current authored CredentialRevision
- Credential has zero or one active/preferred SecretVersion for new execution

Different provider accounts should normally be modeled as separate Connections rather than unrelated Credentials under one generic provider Connection.

## Lifecycle

Expected explicit lifecycle: `ACTIVE`, `DISABLED`, `ARCHIVED`.

`DISABLED` is a deliberate runtime kill switch. Authentication validity/health remains separate operational state.

## Authentication Schemes

Schemes come from a typed registry. Initial likely schemes: `API_KEY`, `BEARER_TOKEN`, `BASIC_AUTH`, `CUSTOM_HEADER`, `OAUTH2`.

Each scheme defines configuration schema, secret fields, runtime injection, refresh capability, validation behavior, and redaction rules.

## CredentialRevision

CredentialRevision is immutable and versions authentication semantics independently from secret value.

Examples requiring a new revision: header name/prefix/location change, signing behavior change, auth configuration change.

Published Bindings pin an exact CredentialRevision.

## CredentialSecretVersion

Secret versions are immutable and store encrypted material plus encryption metadata, version number, safe hint where applicable, and activation/revocation/destruction metadata.

Ciphertext is never updated in place.

## Binding Relationship

BindingRevision pins Credential identity and CredentialRevision, but not CredentialSecretVersion.

Routine secret rotation does not require republishing every Binding. Runtime resolves the active SecretVersion at execution time. ExecutionAttempt records the exact SecretVersion actually used.

## Envelope Encryption

Secret material uses provider-neutral envelope encryption backed by an external KMS/key-management abstraction. Database compromise alone must not reveal customer credential plaintext.

Control plane should not require routine decrypt permission. Execution plane decrypts only when execution requires it.

## Customer Read Semantics

Secrets are write-only after submission. UI/API may show a safe hint, but cannot reveal original secret. Replacing a secret creates a new SecretVersion.

## Runtime Resolution

Plaintext credentials must never be written to Postgres, RabbitMQ payloads, Valkey, execution history, logs, traces, or debug dumps. Distributed plaintext secret caching is prohibited.

## Rotation

Rotation creates a new immutable SecretVersion. Safe lifecycle may support `PENDING`, `ACTIVE`, `RETIRING`, `REVOKED`, `DESTROYED`.

External validation occurs outside long DB transactions. Activation is concurrency-safe and uses row locking or expected-current-version semantics.

## OAuth

OAuth uses the same Credential domain. Long-lived/root sensitive material belongs to encrypted Credential secret state. Short-lived access tokens may use encrypted mutable OAuthTokenState rather than generating endless SecretVersions.

OAuth refresh uses concurrency control. Rotating refresh-token providers require atomic persistence of new refresh/access state.

## Health and Validation

Credential lifecycle and health are separate. Operational health may report `VALID`, `UNKNOWN`, `EXPIRED`, `AUTH_FAILED`, `REAUTH_REQUIRED`.

A single upstream 401 does not automatically disable a Credential.

## Project Access

Connection remains the principal Project-access boundary initially. Different provider accounts should normally be separate Connections. Credential-level ACLs are deferred unless a real use case appears.

## Automatic Fallback

Runtime does not automatically try a different Credential when the configured one fails. Cross-identity fallback must be explicitly modeled if ever added.

## Runtime Admission

A cached BindingRevision cannot override `Credential.DISABLED`. If an active Credential has no usable SecretVersion, runtime returns a normalized configuration failure such as `CREDENTIAL_UNAVAILABLE`.

## Redaction and Audit

Credential material is automatically sensitive. Audit records lifecycle/configuration events but never secret material.

ExecutionAttempt records Credential ID, CredentialRevision ID, and CredentialSecretVersion ID for forensic lineage.

## Frozen Invariants

1. Credential belongs to exactly one Connection and Workspace.
2. Connection represents the logical external account/environment boundary.
3. Credential is authentication identity, not secret material.
4. Authentication behavior/configuration is represented by immutable CredentialRevision.
5. Secret material is represented by immutable CredentialSecretVersion.
6. BindingRevision pins Credential and CredentialRevision, not SecretVersion.
7. Runtime resolves the currently active SecretVersion at execution time.
8. ExecutionAttempt records the exact SecretVersion actually used.
9. Routine secret rotation does not require Binding republish.
10. Authentication-semantic changes require a new CredentialRevision and subsequent Binding publication.
11. Secret ciphertext is never updated in place.
12. Secrets are write-only to customers after submission.
13. Plaintext secrets are never persisted in DB, queues, caches, execution history, logs, or telemetry.
14. Database compromise alone should not reveal credential plaintext.
15. Secret encryption uses envelope encryption backed by an external KMS abstraction.
16. Control plane does not require routine secret decryption.
17. Execution plane decrypts only at the last responsible moment.
18. Credential has an explicit mutable kill switch.
19. Cached Binding configuration cannot override disabled Credential state.
20. Secret revocation and Credential disable are different states.
21. Credential health/auth validity is operational state separate from explicit lifecycle.
22. Secret rotation/activation is transactional and concurrency-safe.
23. Network validation occurs outside long DB transactions.
24. OAuth access tokens may use encrypted mutable operational state rather than generating endless SecretVersions.
25. Rotating OAuth refresh tokens are handled atomically by provider-specific Credential logic.
26. Provider/auth adapters cannot bypass central outbound HTTP security.
27. Credential material is automatically sensitive for redaction.
28. Historical CredentialRevision/SecretVersion metadata may remain after secret material is destroyed.
29. Hard deletion is not normal lifecycle while historical references exist.
30. Automatic Credential fallback is not supported unless explicitly modeled later.

---


# 6. Operation / OperationVersion

## Purpose

Operation is the stable semantic identity of a backend capability.

OperationVersion is the complete immutable executable contract for one authored revision of that capability.

Examples:

- `Create Contact`
- `Search Products`
- `Upload Asset`
- `Download Invoice PDF`

Operation answers **what capability exists**.

OperationVersion answers **exactly how that capability executes**.

## Ownership and Cardinality

Operation belongs to exactly one Workspace and exactly one Connection.

- Connection `1 -> N Operation`
- Operation `1 -> N OperationVersion`

`Operation.connection_id` is immutable during ordinary lifecycle.

An Operation cannot dynamically choose an arbitrary Connection at runtime.

## Operation Lifecycle

Expected states:

- `ACTIVE`
- `DISABLED`
- `ARCHIVED`

`DISABLED` acts as a global capability kill switch across Bindings using the Operation.

Archiving preserves all historical versions and execution lineage.

## OperationVersion Immutability

OperationVersion is immutable after creation.

Executable changes create another version rather than modifying an existing version in place.

The authoring UI may maintain temporary unsaved draft state, but persisted executable versions are immutable records.

Version numbers are monotonic per Operation and concurrency-safe.

## Definition Contract

OperationVersion uses a versioned, validated executable definition document, expected to be stored as JSONB plus a canonical integrity hash.

The executable-contract schema version is distinct from the customer's Operation version number.

Example dimensions:

- `operation_version = 8`
- `definition_schema_version = 2`

Provider-native and generic HTTP Operations use the same Operation/OperationVersion model, even where their provider-specific definition schemas differ.

## V1 Request Body Modes

The following request body modes are first-class V1 capabilities:

- `NONE`
- `JSON`
- `FORM_URLENCODED`
- `MULTIPART`
- `RAW`

These are part of the canonical execution contract from the first production version; they are not future placeholders.

### NONE

No request body is emitted.

Typical examples:

- GET requests
- DELETE requests without body

### JSON

The executor renders and serializes a JSON document from validated inputs, literals, and safe context values.

### FORM_URLENCODED

The executor produces `application/x-www-form-urlencoded` payloads from explicitly mapped fields.

### MULTIPART

The executor supports multipart requests containing structured fields and file parts.

This is a V1 requirement for file/image/PDF uploads and APIs requiring multipart form submission.

Each file part must have explicit metadata and limits, including where applicable:

- field name
- content type
- filename
- maximum size
- accepted MIME types

The executor must stream multipart file content where practical rather than buffering arbitrarily large uploads into memory.

### RAW

The executor supports an explicit raw request body with a declared content type.

RAW does not mean unrestricted arbitrary transport. Input shape, size, caller-controlled content, and allowed content types remain bounded by OperationVersion and platform policy.

## V1 Response Modes

The following response modes are first-class V1 capabilities:

- `JSON`
- `TEXT`
- `BINARY`
- `STREAM`

The executor and runtime API must be designed around these modes from V1 rather than assuming every upstream response becomes buffered JSON.

### JSON

Structured JSON response.

Supports schema validation and declarative projection/transformation.

### TEXT

Textual response with bounded character/byte size and safe content-type handling.

### BINARY

Finite binary payload returned as a file/blob response.

First-class V1 use cases include:

- PDF download
- image download
- generated documents
- ZIP/archive download
- other bounded file responses

The runtime should preserve or deliberately derive safe metadata such as:

- MIME type
- content length where known
- filename / Content-Disposition where allowed

Unsafe upstream headers are never blindly forwarded.

### STREAM

Streaming response where data is forwarded incrementally rather than fully buffered.

V1 streaming is required for large downloads and streaming-compatible upstream APIs.

Streaming execution must still enforce:

- timeout/deadline
- maximum transferred bytes where policy requires
- connection cancellation
- safe response headers
- telemetry
- caller disconnect propagation where possible

Streaming must not bypass normal execution admission, credential, SSRF, or observability controls.

## V1 File / Media Support

PDF, images, file upload, and file download are first-class V1 product capabilities.

They are represented through the canonical request/response body modes rather than separate incompatible execution systems.

Typical mapping:

```text
File / image / PDF upload
    -> MULTIPART or RAW request

File / image / PDF download
    -> BINARY or STREAM response
```

PDF/image are media/MIME semantics rather than separate transport-mode enums.

The contract must support at minimum:

- MIME type validation
- filename metadata where relevant
- bounded file size
- upload/download byte accounting
- streaming where appropriate
- content-disposition handling
- safe header allowlisting
- cancellation and timeout handling

## Memory / Buffering Rule

The execution engine must not assume entire request/response bodies fit in memory.

JSON/TEXT may be buffered within explicit limits.

MULTIPART, RAW, BINARY, and STREAM paths must be designed so large payloads can be handled incrementally where practical.

This is a V1 architectural requirement because adding streaming after a JSON-only runtime would otherwise require changing the transport abstraction and executor pipeline.

## Input Contract

Every OperationVersion exposes an explicit validated input contract, expected to use JSON Schema plus controlled platform extensions.

Caller-controlled values are explicitly enumerated.

`additionalProperties: false` should be the default for public input objects unless explicitly overridden for a safe reason.

Sensitive fields may be marked through platform schema metadata and are automatically redacted from observability.

Credential material remains sensitive independently of Operation input metadata.

## File Input Contract

File-bearing inputs require explicit file constraints rather than arbitrary blobs.

The input contract must be able to express at least:

- file required/optional
- accepted MIME types
- maximum bytes
- single vs multiple files where supported
- filename handling

File inputs must participate in normal payload/usage accounting and entitlement enforcement.

## Privileged Parameters

Runtime callers cannot arbitrarily control privileged execution parameters such as:

- upstream host/base URL
- Connection identity
- Credential identity
- HTTP method
- auth injection behavior
- unrestricted headers

unless an Operation explicitly exposes a bounded safe choice.

This preserves the no-open-proxy security model.

## Request Construction

Request construction is declarative.

Supported value sources conceptually include:

- literal
- validated caller input
- controlled execution context
- authentication injection

Credential material should be injected through the Credential/Auth subsystem rather than generic user-defined templates.

V1 does not support arbitrary server-side JavaScript/eval/filesystem/network code inside Operation definitions.

## Response Projection / Transformation

OperationVersion may expose a controlled output contract rather than returning every upstream field.

JSON responses can support declarative transformations such as:

- field selection
- rename
- nesting/flattening
- array mapping
- defaults
- bounded simple conditions

V1 transforms are not an arbitrary programming language.

For `BINARY` and `STREAM`, structured JSON transforms do not apply. File/media handling uses explicit response metadata and safe passthrough rules instead.

For `TEXT`, only bounded text-safe transforms should be permitted if any are implemented.

## Response Validation

JSON OperationVersions may optionally define an expected response schema.

Response validation can support upstream contract-drift detection and stronger downstream bindings.

It need not be mandatory for every generic API operation.

Binary/file response validation focuses on declared properties such as MIME type, size, and other explicitly supported metadata rather than JSON schema.

## Side-Effect Classification

HTTP method alone does not determine semantic behavior.

OperationVersion explicitly declares:

- `READ`
- `WRITE`

This classification drives Binding compatibility, caching safety, retry behavior, and UX warnings.

A QUERY Binding cannot expose a WRITE OperationVersion.

An ACTION may invoke either class where useful.

## Retry Policy

Retry semantics belong to OperationVersion because safety is determined by upstream operation behavior.

Retry configuration is bounded by platform-wide safety caps.

Read Operations may allow limited safe retries for transport/selected upstream failures.

Write Operations must not be blindly retried.

## Idempotency Semantics

OperationVersion explicitly describes upstream idempotency semantics.

Potential modes include:

- no safe retry/idempotency support
- naturally idempotent operation
- upstream idempotency key

Where upstream idempotency keys are supported, the definition specifies their safe injection location/name.

Internal platform idempotency never implies that an external non-idempotent side effect is safe to retry.

## Indeterminate Results

If a write may have reached upstream but the outcome cannot be observed, execution can become `INDETERMINATE`.

Runtime must not blindly retry an indeterminate non-idempotent write.

This status is part of the durable execution/error model.

## Timeout / Size Policy

OperationVersion may request execution limits such as timeout and maximum response size.

Effective limits are bounded by:

- platform security maximums
- Connection/security policy
- Entitlements
- Binding policy where applicable

No Operation may override platform safety ceilings.

File upload/download limits follow the same layered effective-policy model.

## Redirect / Network Policy

Secure central HTTP transport remains authoritative for:

- SSRF prevention
- DNS/IP validation
- redirect safety
- TLS requirements
- connection timeout
- maximum body transfer
- cancellation
- telemetry

OperationVersion may select only bounded safe redirect/network options exposed by that transport.

## Cache Semantics

OperationVersion may declare whether a READ response is intrinsically cache-eligible.

Actual cache enablement and TTL belong to BindingRevision because exposure policy may differ per Project.

WRITE Operations are not response-cacheable unless a future explicit semantic model safely permits it.

## Connection / Credential Composition

OperationVersion does not pin ConnectionRevision.

Operation belongs to stable Connection identity.

BindingRevision composes the concrete ConnectionRevision used in production.

OperationVersion also does not pin Credential/CredentialRevision.

BindingRevision selects the authorized Credential identity/revision.

This avoids creating duplicate OperationVersions for Connection configuration updates or credential changes that do not alter Operation semantics.

## Provider-Native Operations

Provider-native operations use the same canonical execution engine.

A provider adapter may compile provider-specific definitions into execution requests, but does not own a separate hidden HTTP executor.

All provider traffic remains subject to central transport/security/telemetry controls.

## Publish-Time Compilation

Authoring definitions are validated and compiled before production publication.

Conceptually:

`OperationVersion + ConnectionRevision + CredentialRevision + BindingRevision -> ExecutableBindingRevision`

Publish-time compilation should reject incompatible or invalid combinations before production traffic reaches them.

Examples:

- template references nonexistent input
- request mode incompatible with definition
- file input mapped to JSON-only request
- response transform incompatible with BINARY/STREAM
- provider/auth incompatibility
- QUERY binding points to WRITE Operation

Runtime should execute cached compiled immutable artifacts rather than repeatedly interpreting authoring configuration.

## Definition Hash

Every immutable OperationVersion has a canonical content hash, expected to use SHA-256 over canonicalized definition content.

The hash supports integrity checks, duplicate detection, compilation caching, and diagnostics.

## Database Integrity

Expected constraints include:

- Operation `(workspace_id, connection_id)` -> Connection
- OperationVersion `(workspace_id, operation_id)` -> Operation
- unique `(operation_id, version_number)`
- immutable Workspace/Connection ownership during ordinary lifecycle

Tenant-aware composite foreign keys are preferred where practical.

## Scalability

Operation/OperationVersion are low-volume control-plane state.

No partitioning expected.

Definition JSONB may grow moderately but remains configuration rather than runtime data.

Compiled runtime artifacts are cached separately and keyed by immutable revision identities/hashes.

## Frozen Invariants

1. Operation belongs to exactly one Workspace and one Connection.
2. Operation Connection ownership is not ordinarily mutable.
3. Operation is semantic identity; OperationVersion is executable definition.
4. OperationVersion is immutable.
5. Persisted executable changes create a new OperationVersion.
6. The executable definition schema is explicitly versioned independently from Operation version number.
7. OperationVersion uses a typed/validated versioned contract rather than arbitrary unvalidated JSON.
8. V1 request modes are `NONE`, `JSON`, `FORM_URLENCODED`, `MULTIPART`, and `RAW`.
9. V1 response modes are `JSON`, `TEXT`, `BINARY`, and `STREAM`.
10. PDF, image, file upload, and file download are first-class V1 capabilities.
11. PDF/image/file semantics use MIME/file metadata layered over canonical body modes rather than separate execution engines.
12. Large file/stream paths must not require full in-memory buffering.
13. Input contracts explicitly enumerate caller-controlled fields.
14. Additional arbitrary caller properties are rejected by default.
15. Sensitive input fields can be automatically redacted.
16. File inputs declare MIME/size and other bounded constraints.
17. Runtime callers cannot arbitrarily choose host, Connection, Credential, HTTP method, or unrestricted privileged execution parameters.
18. Request construction is declarative and sandboxed; arbitrary server-side code is not part of V1.
19. Credential injection occurs through Credential/Auth infrastructure rather than generic templating.
20. JSON output may be explicitly projected/transformed rather than blindly exposing complete upstream responses.
21. BINARY/STREAM use explicit safe file/response metadata rather than JSON transforms.
22. Response validation is supported according to response mode and may be optional where appropriate.
23. OperationVersion declares semantic side-effect classification independently from HTTP method.
24. QUERY Bindings cannot expose WRITE Operations.
25. Retry semantics belong to OperationVersion and are platform-bounded.
26. Upstream idempotency semantics are explicit.
27. Non-idempotent ambiguous upstream outcomes may become `INDETERMINATE`; runtime does not blindly retry them.
28. Timeout, size, and transfer limits are bounded by platform/security/entitlement policy.
29. Central secure HTTP transport remains authoritative for SSRF, redirect, DNS/IP, TLS, cancellation, and transfer safety.
30. OperationVersion does not pin ConnectionRevision.
31. OperationVersion does not pin Credential or CredentialRevision.
32. BindingRevision composes exact OperationVersion, ConnectionRevision, and CredentialRevision for production exposure.
33. Native provider Operations use the same canonical execution engine.
34. OperationVersion has a canonical content hash.
35. Version numbering is monotonic per Operation.
36. Operation disable/archive blocks new runtime use without destroying historical versions.
37. Runtime uses compiled immutable artifacts rather than reparsing/recompiling authoring definitions on every request.

---

# Current Aggregate Map — Reconciled

```text
User
└── WorkspaceMembership ── Workspace

Workspace
├── WorkspaceInvitation
├── Project
│   ├── FramerProjectLink
│   ├── Binding
│   │   ├── BindingRevision
│   │   └── BindingPublicIdentifier (PUBLIC bindings only)
│   ├── JobDefinition
│   │   ├── JobRevision
│   │   └── JobRun
│   ├── WebhookEndpoint
│   │   ├── WebhookEndpointRevision
│   │   ├── WebhookEndpointSecretVersion
│   │   └── WebhookDelivery
│   └── SyncDefinition
│       ├── SyncDraft
│       ├── SyncRevision
│       ├── SyncRun
│       │   └── SyncRunItem
│       ├── SyncMapping
│       └── SyncCheckpoint
│
├── Connection
│   ├── ConnectionRevision
│   ├── ConnectionProjectAccess
│   ├── Credential
│   │   ├── CredentialRevision
│   │   ├── CredentialSecretVersion
│   │   └── OAuthTokenState
│   └── Operation
│       └── OperationVersion
│
├── BillingAccount
│   └── Subscription
│       └── SubscriptionItem
├── EntitlementGrant
├── ProjectProfileAssignment
├── UsageEvent
├── UsageBucket
├── Notification
│   └── NotificationDelivery
│       └── NotificationDeliveryAttempt
├── NotificationPreference
├── OutboxEvent
├── ConsumerDeduplication
└── AuditEvent

Runtime history
└── Execution
    └── ExecutionAttempt

IdempotencyRecord binds stable public Action request identity to one logical Execution.
```

## Reconciliation decisions applied at schema freeze

1. Binding has two independent axes: `kind = QUERY|ACTION` and `exposure_mode = PUBLIC|INTERNAL`.
2. Only PUBLIC Bindings have active public runtime identifiers. INTERNAL Bindings are reusable by Jobs, Webhooks and Sync without exposing a browser endpoint.
3. JobRevision targets exactly one of Binding or SyncDefinition. JobRun pins the exact JobRevision and, for Binding jobs, exact BindingRevision; Sync-target jobs create a SyncRun pinned to its SyncRevision.
4. Sync core is provider-neutral. Framer-specific identities and CMS behavior live in adapter configuration, not generic Sync tables.
5. Historical runtime rows carry exact immutable revision/version IDs. Mutable `active_revision_id`/current pointers are authoring/admission conveniences only.
6. Execution is the canonical logical invocation. Automatic retries are ExecutionAttempts; manual replay creates a new Execution.
7. Webhook provider retries dedupe into one WebhookDelivery; internal retries remain ExecutionAttempts.
8. RabbitMQ is transport. PostgreSQL domain rows and OutboxEvent state are authoritative.
9. Customer Notification delivery and platform SRE alerting remain separate systems.
10. AuditEvent is append-only accountability data and never substitutes for runtime history or domain truth.

---

# Open Decisions

Intentionally deferred:

- exact commercial pricing
- exact usage allowances
- deployment provider
- infrastructure SKU/cost
- final authentication provider
- whether Project-level ACL restrictions ship initially
- precise Framer authorization implementation
- final retention durations
- eventual generic Environment aggregate
- exact runtime cache/invalidation mechanism for mutable admission state


---

# 7. Binding / BindingRevision

## Purpose

Binding is a stable Project-local exposure identity.

BindingRevision is the immutable published composition that runtime executes.

A Binding answers: **How does this Project expose this backend capability?**

Operation is the reusable backend capability; Binding is the Project-specific exposure.

## Ownership

Binding belongs to exactly one Workspace and one Project. One Project may have many Bindings.

Binding `workspace_id` and `project_id` are immutable in ordinary operation.

## Kind

Initial Binding kinds are `QUERY` and `ACTION`. Query and Action are not separate aggregate tables.

OperationVersion independently declares semantic effect as `READ` or `WRITE`. A QUERY Binding may not expose a WRITE OperationVersion. An ACTION may expose READ or WRITE behavior.

## Exposure Mode

Binding exposure mode is independent from QUERY/ACTION semantics.

- `PUBLIC` — callable through a public runtime identifier and browser/server ingress policy.
- `INTERNAL` — callable only from trusted platform workflows such as Jobs, Webhooks and Sync; it has no public runtime identifier.

This keeps one canonical capability-composition model without creating unnecessary public endpoints for background work.

## Stable Identity

Binding is long-lived identity. Expected fields include `id`, `workspace_id`, `project_id`, `name`, `kind`, lifecycle status, `active_revision_id`, and creation/update metadata. Runtime exposure identity is separate from internal primary identity.

## Lifecycle

Expected lifecycle: `DRAFT`, `ACTIVE`, `DISABLED`, `ARCHIVED`. A Binding may exist before first successful publication. `DISABLED` is an immediate kill switch for new runtime admissions. Archiving prevents normal execution/publication while preserving history.

## BindingRevision

BindingRevision is immutable and represents successfully validated published composition, not autosave/draft state. If persistent drafts are required later they use a separate `BindingDraft` concept.

## Exact Composition

BindingRevision pins exact immutable references to Operation, OperationVersion, Connection, ConnectionRevision, Credential, and CredentialRevision. It does not pin CredentialSecretVersion. Routine secret rotation therefore does not require Binding republish. Runtime resolves the current usable SecretVersion, while ExecutionAttempt records the actual SecretVersion used.

## Denormalized Identity for Integrity

BindingRevision may explicitly carry otherwise derivable IDs such as `project_id`, `connection_id`, `operation_id`, and `credential_id` in addition to their version/revision IDs. This intentional denormalization improves tenant-aware composite FK enforcement, cross-aggregate integrity, runtime/config queries, and forensic readability.

## Publication

Publishing is atomic: construct candidate BindingRevision, validate the complete composition, compile the runtime artifact, persist the immutable revision, and atomically switch `Binding.active_revision_id`. There must be no partially published state.

## Publication Validation

Publication validates at least: same-Workspace ownership, Operation-to-Connection compatibility, revision ownership, Credential ownership, Project access to Connection, QUERY/WRITE incompatibility, input/output mappings, template compilation, body/response mode compatibility, auth compatibility, origin/CORS policy, cache policy, and platform-bounded rate/runtime limits. Basic incompatibilities should be discovered at publish time rather than during production traffic.

## Rollback

Rollback atomically repoints `Binding.active_revision_id` to an earlier immutable BindingRevision after re-validating current mutable admission dependencies. An old revision may remain non-runnable if a referenced Connection or Credential has since been disabled.

## In-Flight Execution

Each accepted request resolves one active BindingRevision and remains pinned to it for the full logical Execution. Publishing a newer revision does not alter in-flight work. Disabling a Binding rejects new admissions but does not blindly terminate already accepted mutations.

## Public Runtime Identifier

Public runtime identity belongs to Binding rather than BindingRevision. The endpoint remains stable while `active_revision_id` changes. Public identifiers are not authentication secrets and must not be relied on for authorization.

## Public Identifier Lifecycle

Public IDs are independently rotatable/revocable. A likely model is historical `BindingPublicIdentifier` records with activation/revocation timestamps and normally one active public identifier.

## Origin Policy

BindingRevision owns exposure-specific origin policy. Likely modes include `PROJECT_DOMAINS` and `EXPLICIT`. `PROJECT_DOMAINS` may resolve current verified Project domains dynamically; `EXPLICIT` pins specific origins. Origin validation is an abuse/browser control, not authentication.

## Input Exposure

OperationVersion defines the complete input contract. BindingRevision determines which values callers may supply and which are supplied server-side. Runtime input flow is `caller input -> Binding input policy -> validated Operation input`. The caller cannot directly override privileged inputs.

## Output Exposure

OperationVersion defines canonical output. BindingRevision may further restrict/project output exposed through this Project capability.

## Cache Policy

OperationVersion declares whether caching is safe/eligible. BindingRevision owns actual exposure cache policy. Initial QUERY cache modes may include `NONE` and `TTL`. ACTION caching is not supported as normal behavior.

## Rate / Runtime Policy

BindingRevision may request exposure-specific rate limits, input/output size limits, and timeout restrictions. Effective runtime policy is the most restrictive applicable combination of Operation policy, Binding policy, platform safety bounds, and current Entitlements.

## CORS

Browser-facing CORS belongs to Binding exposure policy and should be generated/validated from safe supported options rather than arbitrary unsafe configuration. CORS/origin policy is separate from upstream network/SSRF policy.

## Invocation Authentication

V1 supports public visitor-triggered Binding execution. End-user application authentication is not assumed. Additional signed/server modes may be introduced where a concrete V1 use case requires them.

## Action Idempotency Policy

For ACTION Bindings, external invocation idempotency policy belongs to BindingRevision, with likely modes `DISABLED`, `SUPPORTED`, and `REQUIRED`. OperationVersion separately describes upstream side-effect idempotency/retry semantics. Public Action idempotency uniqueness is scoped to stable Binding identity, not BindingRevision. Same-key retries reuse the original logical Execution even if a newer revision is active.

## Runtime Admission

Semantic checks include: Binding active, Workspace active, Project active, Connection active, Credential active, usable Credential secret, Project access to Connection, Entitlement permission, and rate/quota admission. Implementation may reorder lookups for efficiency, but these semantic checks remain.

## Executable Runtime Artifact

Publication compiles control-plane state into an immutable `ExecutableBindingRevision` containing identities, compiled request/response programs, validated input contract, compiled exposure/security policy, and a canonical configuration hash. Runtime loads this artifact rather than joining and recompiling the relational graph per request.

## Configuration Hash

Every BindingRevision receives a canonical configuration hash used for immutable cache identity, integrity validation, duplicate publication detection, diagnostics, and rollout verification.

## Cache Shape

Immutable revision artifacts never require invalidation. Only the small mutable surface does: public ID mapping, Binding active revision/lifecycle, Workspace/Project/Connection/Credential lifecycle, Project-to-Connection access, and Entitlement/quota state.

## Database Integrity

Expected tenant-aware relationships include Binding-to-Project and BindingRevision-to-Binding/OperationVersion/ConnectionRevision/Credential/CredentialRevision. Redundant parent IDs may be carried specifically so composite FKs can prove that the composition belongs to one consistent tenant graph.

## Scalability

Binding and BindingRevision are low-volume control-plane state. No partitioning is expected. Active-revision lookup is hot and should be aggressively cacheable.

## Frozen Invariants

1. Binding belongs to exactly one Project and Workspace.
2. Binding is stable Project-local exposure identity.
3. Initial Binding kinds are QUERY and ACTION.
4. QUERY may not expose a WRITE OperationVersion.
5. Binding exposure mode is `PUBLIC` or `INTERNAL`, independent from QUERY/ACTION kind.
6. PUBLIC Bindings own stable public runtime exposure identity; INTERNAL Bindings have no public runtime identifier.
7. Public Binding identifiers are not authentication secrets and are independently rotatable/revocable.
8. Binding has a mutable runtime kill switch.
9. BindingRevision is immutable.
10. BindingRevision represents successfully validated published state, not a mutable draft.
11. Publishing creates a new BindingRevision and atomically switches `active_revision_id`.
12. Rollback repoints to an older immutable revision after current admission compatibility validation.
13. BindingRevision pins exact OperationVersion, ConnectionRevision, Credential, and CredentialRevision.
14. BindingRevision does not pin CredentialSecretVersion.
15. Routine secret rotation does not require Binding publication.
16. BindingRevision owns Project-specific input exposure/mapping policy.
17. BindingRevision owns exposure-specific output policy.
18. For PUBLIC Bindings, BindingRevision owns origin/CORS exposure policy; INTERNAL Bindings do not require browser exposure semantics.
19. BindingRevision owns actual cache policy while OperationVersion determines cache eligibility.
20. BindingRevision owns exposure-specific rate/runtime restrictions within platform/entitlement bounds.
21. Runtime callers cannot choose arbitrary Operation, Connection, Credential, destination, or privileged inputs.
22. Publication validates the complete cross-aggregate composition before activation.
23. Publication compiles an immutable runtime artifact.
24. Runtime does not rebuild authoring configuration for every request.
25. Each accepted request resolves one BindingRevision and remains pinned to it.
26. Publishing a new revision does not affect in-flight executions.
27. Disabling a Binding rejects new admissions but does not blindly abort accepted mutations.
28. ACTION invocation idempotency policy belongs to BindingRevision.
29. Public Action idempotency uniqueness is scoped to stable Binding identity rather than BindingRevision.
30. Same-key retries reuse the original logical Execution even if active BindingRevision later changes.
31. Mutable Workspace/Project/Connection/Credential/Entitlement state can block execution despite valid immutable BindingRevision.
32. Project-to-Connection access is enforced at publication and runtime.
33. BindingRevision receives a canonical configuration hash.
34. Runtime caching separates mutable admission/pointer state from immutable revision artifacts.
35. Hard deletion is not normal lifecycle while historical Execution records reference Binding.

## Cardinality

- Project `1 -> N Binding`
- Binding `1 -> N BindingRevision`
- PUBLIC Binding `1 -> N historical BindingPublicIdentifier`, normally `0..1` active; INTERNAL Binding has none
- Each BindingRevision references exactly one OperationVersion, ConnectionRevision, Credential, and CredentialRevision


---

# 8. Execution / ExecutionAttempt

## Purpose

Execution represents one logical invocation. ExecutionAttempt represents one concrete processing attempt of that invocation.

Automatic retries create additional Attempts under the same Execution. Manual replay creates a new Execution linked to the original.

## Ownership and Lineage

Execution explicitly stores `workspace_id`, `project_id`, Binding/BindingRevision, Operation/OperationVersion, Connection/ConnectionRevision, and Credential/CredentialRevision lineage. Attempt stores the exact CredentialSecretVersion used.

This deliberate denormalization keeps high-volume operational queries tenant/project scoped without requiring deep configuration joins.

## Sources

Initial sources:

- `QUERY`
- `ACTION`
- `JOB`
- `WEBHOOK`
- `SYNC`
- `MANUAL_TEST`
- `MANUAL_REPLAY`

## Lifecycle

Non-terminal states:

- `PENDING`
- `RUNNING`

Terminal states:

- `SUCCEEDED`
- `REJECTED`
- `FAILED`
- `INDETERMINATE`
- `CANCELLED`
- `DEAD_LETTERED`

`INDETERMINATE` is first-class when a side-effecting upstream request may have committed but no definitive response was obtained and safe retry cannot be established.

Gross pre-admission garbage/abuse need not create Execution rows. Binding-resolved, customer-relevant rejection may create `REJECTED` Execution with zero Attempts.

## Retry vs Replay

Retry means another Attempt for the same logical Execution.

Replay means a new Execution linked through `replay_of_execution_id`.

Replay defaults to original immutable configuration lineage but resolves currently usable Credential secret material; revoked historical secrets are never resurrected.

## ExecutionAttempt

Attempt records append-oriented processing evidence including:

- attempt number
- start/end timestamps
- result status
- exact CredentialSecretVersion
- upstream status where available
- request/response byte counts
- normalized error code/category
- retryability as evaluated at that time
- trace correlation

Attempt status remains simple; timeout/network/etc. are primarily normalized error categories/codes rather than proliferating lifecycle states.

## Claims, Leases, and Fencing

Async processing may use Execution claim/lease state to reduce duplicate concurrent work.

Lease expiry is not proof the old worker stopped. Correctness therefore assumes duplicate Attempts remain possible.

A monotonic attempt/fencing value prevents stale Attempts from overwriting newer Execution state. Fencing protects our database state only; it does not provide exactly-once remote side effects.

## Retry Semantics

Retry decisions combine:

- OperationVersion retry policy
- upstream idempotency semantics
- normalized error
- attempt count
- platform caps

Error category alone does not imply retryability.

## Payload Retention

Execution is durable metadata. Optional sanitized payload retention is separate and shorter-lived.

Credential material and sensitive inputs are always redacted. Binary/stream bodies are generally not retained; metadata such as MIME type, filename, byte count, and safe hashes may be retained where useful.

Large retained payloads must be abstractable to object storage rather than making Postgres a blob store.

## Streaming and Files

STREAM/BINARY/file upload/download use the same Execution model.

Streaming begins while Execution remains RUNNING; terminal state is recorded when the stream completes/fails. Large payloads should stream rather than buffer where practical.

## Partitioning

Execution and ExecutionAttempt are high-volume operational tables designed for time partitioning from the beginning, likely monthly initially.

Useful partition-local indexes include tenant/project/binding + recent time. Retention should be achievable by dropping old partitions rather than massive DELETEs.

## Dead Lettering

RabbitMQ DLQ state is transport state only. Customer-visible dead-letter state is persisted on product records such as Execution/JobRun/WebhookDelivery.

## Usage

Customer-facing execution billing normally meters one logical Execution rather than retry Attempts. Internal cost accounting may meter Attempts and actual bandwidth separately.

## Frozen Invariants

1. Execution is one logical invocation.
2. ExecutionAttempt is one concrete processing attempt.
3. Automatic retries stay within one Execution.
4. Manual replay creates a new linked Execution.
5. Execution records exact immutable runtime lineage.
6. Attempt records exact CredentialSecretVersion used.
7. Terminal history is not silently reopened or rewritten.
8. `INDETERMINATE` is a first-class terminal state.
9. Gross pre-admission abuse need not create durable Execution rows.
10. Binding-resolved customer-relevant rejection may persist as `REJECTED` with zero Attempts.
11. Attempts are append-oriented.
12. At most one active Attempt is intended, but duplicate execution is assumed possible.
13. Leases reduce duplicates but do not provide exactly-once semantics.
14. Fencing prevents stale workers from overwriting newer local state.
15. Fencing does not prevent duplicate remote side effects.
16. Retryability depends on operation semantics plus error conditions.
17. Publishing a new BindingRevision does not change an already accepted Execution.
18. Replay never revives revoked historical secret material.
19. Binary/file contents do not live in Execution rows.
20. Payload retention is separate from metadata retention.
21. Sensitive values are redacted before any payload retention.
22. Execution/Attempt storage is partitionable by time.
23. Workspace and Project are explicit dimensions.
24. Source-specific parents use real FKs where practical.
25. Product-visible dead-letter state is durable and separate from broker DLQ state.
26. Customer billing generally meters logical Execution rather than retries.
27. Trace correlation exists without turning the product DB into a tracing backend.
28. `INDETERMINATE` reconciliation, if later supported, is additive rather than destructive rewriting of original evidence.


---

# 9. IdempotencyRecord

## Purpose

IdempotencyRecord provides durable deduplication and result reuse for externally repeatable logical requests, especially ACTION invocations.

It does not claim exactly-once execution and does not by itself make an upstream side effect idempotent.

## Scope

Public ACTION idempotency is scoped to stable Binding identity rather than BindingRevision.

This means the same caller key cannot execute again merely because a new BindingRevision was published between the original request and a retry.

A record captures the BindingRevision and Execution actually selected for the winning request.

## Core Identity

Conceptual uniqueness:

`UNIQUE(workspace_id, binding_id, key_hash)`

The raw caller key is not stored. A keyed/HMAC-derived hash is preferred over a plain raw hash where appropriate.

Project ID may be stored redundantly for tenant/project queryability and integrity.

## Request Equivalence

The winning request stores a canonical `request_hash` derived from the semantically relevant caller request after normalization.

A duplicate key with the same request hash reuses the existing logical request state/result.

A duplicate key with a different request hash is rejected with a stable error such as `IDEMPOTENCY_KEY_REUSED`.

This prevents accidental or malicious key reuse for different operations.

## Lifecycle

Expected states:

- `PROCESSING`
- `SUCCEEDED`
- `FAILED`
- `INDETERMINATE`

A record may point to the associated Execution from creation onward.

Result metadata may include safe response status and a response/result reference suitable for replaying the original caller-visible result without re-executing the side effect.

## Reservation Flow

Conceptually:

1. resolve Binding and idempotency policy
2. canonicalize caller request
3. compute key hash and request hash
4. transactionally insert/reserve IdempotencyRecord under unique constraint
5. only the winner creates/owns the logical Execution
6. duplicate same-key/same-request callers observe PROCESSING or reuse terminal result
7. same-key/different-request callers are rejected

The database unique constraint is the final concurrency authority.

Valkey may accelerate lookups but is never authoritative.

## Concurrency

The design must tolerate two identical requests arriving simultaneously on different runtime instances.

Correctness comes from the durable uniqueness constraint and transactional winner selection, not distributed locks alone.

Losers must never create a second side-effecting Execution.

## Binding Revision Changes

If the first request executes BindingRevision 7 and Revision 8 becomes active before a retry, the retry with the same key returns/reuses the Revision-7 logical Execution/result.

Idempotency therefore stabilizes the logical request across publication changes.

## Upstream Idempotency

Internal IdempotencyRecord prevents duplicate logical admission inside our platform.

It cannot resolve this ambiguity alone:

- upstream mutation commits
- connection fails before response

If the upstream supports idempotency keys, runtime propagates a deterministic key according to OperationVersion policy.

If the upstream does not support safe retry semantics and outcome is ambiguous, Execution/IdempotencyRecord becomes `INDETERMINATE` rather than blindly retrying.

## Result Reuse

A terminal duplicate should normally return the same safe caller-visible response semantics as the original request without re-running the upstream operation.

Large/binary response reuse may store a bounded durable result reference rather than copying blobs into IdempotencyRecord.

Retention of reusable result material may be shorter than retention of dedupe identity if necessary, but the behavior after result eviction must be explicitly defined.

## Retention

Idempotency retention is independent from execution-log retention.

TTL depends on semantic surface. Examples:

- browser ACTION keys: bounded window
- provider webhook event IDs: longer window
- scheduled occurrence identity: tied to schedule/history requirements
- billing/security events: potentially much longer

Deleting dedupe state too early can re-enable duplicate side effects.

## Failure Semantics

`FAILED` does not automatically mean the same key may execute again.

The original logical request remains associated with its result unless policy explicitly defines a retryable reservation release before any side effect could have occurred.

Once execution may have reached upstream, the idempotency key must remain bound to that logical Execution.

## Security and Privacy

Raw idempotency keys and sensitive request material are not logged.

Request hashing uses canonicalized semantically relevant fields and must avoid unstable transport metadata.

## Other Deduplication Surfaces

IdempotencyRecord is the public ACTION pattern, but the same architectural principle appears elsewhere with domain-specific identity:

- webhook: `(endpoint_id, provider_event_id)`
- scheduled job: `(job_id, scheduled_for)`
- usage event: stable meter dedupe key
- notification: notification type/source dedupe identity
- broker consumer: inbox/message identity where needed

These should not all be forced into one generic polymorphic table if stronger domain constraints are available.

## Scalability

Idempotency is write/read hot but materially smaller than Execution history.

Indexes must support fast key reservation and expiration cleanup.

Time-based cleanup can be driven by `expires_at`; partitioning is optional and should be adopted only if observed volume justifies it.

## Frozen Invariants

1. Platform semantics are at-least-once plus durable idempotency, never exactly-once.
2. Public ACTION idempotency is scoped to stable Binding identity.
3. Raw caller idempotency keys are not stored.
4. Durable database uniqueness decides the winning request under concurrency.
5. Valkey may accelerate but is never authoritative for idempotency.
6. Same key + same canonical request reuses the original logical request/result.
7. Same key + different request is rejected.
8. IdempotencyRecord captures the BindingRevision and Execution selected by the winner.
9. Publishing a new BindingRevision does not allow a same-key retry to execute again.
10. Internal idempotency does not make unsafe upstream mutations idempotent.
11. Upstream idempotency support is explicit OperationVersion policy.
12. Ambiguous unsafe remote side effects become `INDETERMINATE` rather than blind retries.
13. Duplicate callers never create additional logical Executions for the same reservation.
14. `FAILED` does not automatically release a key for re-execution.
15. Once remote side effects may have occurred, the key remains bound to the original Execution.
16. Idempotency retention is independent from execution-log retention.
17. Domain-specific dedupe identities remain in their own domains where that enables stronger integrity.
18. Idempotency/result data never contains credential plaintext or unsanitized sensitive material.


---

# Notification / NotificationDelivery / NotificationDeliveryAttempt / NotificationPreference

## Purpose

Notifications are a dedicated product domain for durable, customer-facing transactional and time-sensitive communication.

Business domains emit facts/events. They do not send email, SMS, or in-app notifications directly.

Examples of producer domains:

- Workspace / Membership
- Billing
- Usage
- Credential
- Job
- Sync
- Security / Identity

The Notification domain owns:

- recipient resolution
- notification preference evaluation
- channel selection
- template selection/versioning
- deterministic rendering
- delivery deadlines
- provider routing
- retry/backoff
- provider callback handling
- dead-letter/final failure state
- customer-visible delivery status where appropriate

Marketing/newsletter communication is intentionally outside this core domain.

## Aggregate Shape

Conceptually:

```text
Business Domain
    |
    v
Domain Event / Outbox
    |
    v
Notification
    |
    +-- NotificationDelivery (EMAIL)
    |      +-- NotificationDeliveryAttempt #1
    |      +-- NotificationDeliveryAttempt #2
    |
    +-- NotificationDelivery (IN_APP)
    |
    +-- future channels
```

A Notification is one logical customer message.

A NotificationDelivery is one channel-specific delivery of that logical message.

A NotificationDeliveryAttempt is one concrete provider attempt.

This mirrors the Execution / ExecutionAttempt reliability model.

## Ownership and Scope

Notification always carries `workspace_id`.

`project_id` is nullable and present when the notification is specifically attributable to one Project.

Notification may target one User, a resolved set of Users, Workspace owners, Workspace admins, billing contacts, or another explicitly supported recipient class.

Producer domains should not normally provide raw email addresses. They provide recipient intent, and the Notification domain resolves recipients and snapshots delivery destinations.

## Recipient Snapshot

Once a Delivery is created, its concrete destination is snapshotted.

A later user email change does not redirect an already-created retry to a different recipient. Future Notifications use the new address.

Recipient destination snapshots are treated as PII and follow explicit retention/redaction policy.

## Logical Notification Identity

Notification represents one logical message caused by one domain fact.

Repeated event delivery must not create duplicate logical Notifications. Notification therefore has a stable dedupe identity.

Example: `workspace_invitation:{invitation_id}:created`.

Expected uniqueness is equivalent to `UNIQUE(notification_type, dedupe_key)` with Workspace scoping where appropriate.

## Source Event

Notification records durable source provenance sufficient for idempotent creation and diagnostics.

The exact persistence shape should avoid weak polymorphic references where stronger integrity is practical.

## Notification Types

Notification types come from a typed registry. Each type defines at least:

- canonical type key
- supported channels
- default priority
- preference behavior
- default template key
- expiration/deadline behavior
- retry class
- whether delivery is required
- whether an in-app copy is expected

Example keys:

- `workspace.invitation`
- `billing.payment_failed`
- `credential.reauth_required`
- `usage.threshold_reached`
- `job.failed`
- `sync.failed`
- `security.account_change`

Business code must not choose provider templates directly.

## Preference Classes

Initial preference classes:

- `REQUIRED`
- `CONFIGURABLE`

Required notifications cannot be suppressed through ordinary notification preferences. Marketing consent/preferences remain outside this domain.

## NotificationPreference

NotificationPreference represents user/workspace preferences for configurable notification types/channels.

Likely dimensions:

- `workspace_id`
- `user_id`
- `notification_type`
- `channel`
- `enabled`
- timestamps

Preference evaluation happens when Notification/Delivery is created. Required types override normal disabled preferences.

## Priority

Initial semantic priority classes:

- `CRITICAL`
- `TRANSACTIONAL`
- `NORMAL`

Priority affects queue/routing urgency and retry timing, not business truth. Priority is domain-defined and bounded.

## Time Sensitivity

Notification explicitly supports `not_before` and `expires_at`.

Transport retry policy must respect the domain deadline. If delivery has not succeeded before `expires_at`, it transitions to `EXPIRED` rather than continuing indefinite retries.

An expired message must not be delivered merely because it remained in a broker retry queue.

## Notification Lifecycle

Expected logical states include:

- `PENDING`
- `PROCESSING`
- `PARTIALLY_DELIVERED`
- `DELIVERED`
- `FAILED`
- `EXPIRED`

For multi-channel messages, logical state is derived from required Delivery outcomes. Notification state never claims more certainty than channel/provider evidence supports.

## NotificationDelivery

NotificationDelivery represents one channel-specific delivery.

Initial channels:

- `EMAIL`
- `IN_APP`

Future channels may be added if requirements justify them.

Expected fields include Notification ID, channel, status, destination snapshot where applicable, template key/version, rendered content reference/snapshot, provider key, provider message ID, and relevant timestamps.

Provider selection belongs to Notification infrastructure, not producer domains.

## Delivery States

Channel delivery may distinguish:

- `PENDING`
- `PROCESSING`
- `PROVIDER_ACCEPTED`
- `DELIVERED`
- `FAILED`
- `BOUNCED`
- `COMPLAINED`
- `EXPIRED`

`PROVIDER_ACCEPTED` does not mean inbox delivery. The system must not report `DELIVERED` merely from provider HTTP acceptance.

## NotificationDeliveryAttempt

DeliveryAttempt is append-oriented. Expected information includes delivery ID, attempt number, timestamps, provider, status, normalized error code/category, retryable-at-time flag, safe provider metadata, and trace/correlation identity.

Raw provider secrets and unrestricted provider payloads are never persisted.

## Retry Semantics

Retry decisions consider NotificationType retry class, channel, normalized provider error, attempt count, `expires_at`, and platform retry caps.

Retry/backoff is bounded. Time-sensitive expiration always overrides transport retry policy. Permanent errors do not retry indefinitely.

## Provider Acceptance Ambiguity

Provider failover must account for indeterminate send state.

If provider acceptance may have occurred but the response was lost, the system must not blindly send through another provider because duplicate customer messages may result.

Automatic cross-provider failover is therefore not assumed safe by default.

## Provider Abstraction

The domain depends on provider-neutral interfaces such as `EmailProvider`. Provider SDKs stay behind Notification adapters.

Changing provider must not alter Workspace, Billing, Job, Sync, or other business-domain logic.

## Durable Creation

Business mutations that require a Notification do not directly perform network delivery.

Correct pattern:

```text
BEGIN
  mutate business state
  insert OutboxEvent
COMMIT

Outbox -> Notification consumer -> Notification/Delivery -> delivery worker
```

Network I/O is never performed inside the originating business transaction.

## Notification Idempotency

At-least-once event delivery must not generate duplicate customer messages.

Logical Notification creation is protected by a stable dedupe key. Delivery provider retries occur under the same NotificationDelivery rather than creating new logical Notifications. Provider callback events are also deduplicated.

## Templates

Transactional templates are versioned. Notification/Delivery records exact template key and template version.

Template changes never alter content for an existing Delivery retry. Retries send the same logical rendered content.

## Rendering

Rendering occurs before provider attempts and produces deterministic delivery content.

A provider retry does not re-render against a newer template or changed mutable business data.

Content is stored as an immutable rendered snapshot or durable reference to immutable rendered content, subject to security/PII retention requirements.

## In-App Notifications

In-app notifications reuse the same logical Notification model. Channel-specific state may include `read_at` and `dismissed_at`.

## Provider Callbacks

Provider delivery callbacks:

1. verify authenticity/signature
2. deduplicate provider event
3. resolve NotificationDelivery
4. apply valid state transition
5. emit telemetry/audit where appropriate

Callbacks cannot arbitrarily regress terminal delivery state.

## Dead-Letter State

Broker DLQ state is not product truth.

If a Delivery exhausts retries or expires, durable product state records the terminal result independently of RabbitMQ.

## Customer Notification vs Platform SRE Alert

Customer/product notifications and platform-operator alerts are separate systems.

Customer examples: sync failed, payment failed, credential requires reauth.

SRE examples: queue age, DB replication lag, runtime 5xx spike, KMS outage.

SRE alerts belong to monitoring/incident tooling, not customer Notification records.

## Security and Privacy

Notification content never includes server credentials/secrets.

Recipient addresses and rendered content follow explicit retention policy.

Sensitive one-time links/tokens retain only what is necessary for delivery/audit.

## Scalability

Notification volume is expected to be lower than Execution volume but still append/history oriented.

Queue priority should use a small bounded set of lanes/classes rather than one queue per notification type.

## Frozen Invariants

1. Notifications are a dedicated domain; producer domains do not send provider messages directly.
2. Business domains emit durable facts/events; Notification owns recipient/channel/template/delivery semantics.
3. Notification is one logical customer message.
4. NotificationDelivery is one channel-specific delivery.
5. NotificationDeliveryAttempt is one concrete provider attempt.
6. Marketing/newsletter communication is outside the core Notification domain.
7. Every Notification belongs to a Workspace.
8. Project is recorded when attribution exists.
9. Producer domains normally specify recipient intent rather than raw destination addresses.
10. Concrete delivery destinations are snapshotted when Delivery is created.
11. Destination changes do not mutate an existing Delivery retry target.
12. Notification creation is idempotent using a stable dedupe identity.
13. At-least-once source-event delivery must not produce duplicate logical customer messages.
14. NotificationType definitions come from a typed registry.
15. NotificationType declares channels, preference behavior, priority, template, expiry, and retry policy.
16. REQUIRED notifications cannot be suppressed by ordinary user preferences.
17. Marketing preferences/consent are not conflated with transactional preferences.
18. Notifications support explicit `not_before` and `expires_at`.
19. Expiration overrides retry/backoff.
20. Semantic priority classes are bounded and domain-defined.
21. Provider acceptance is distinct from confirmed delivery.
22. Delivery status never claims more certainty than provider evidence supports.
23. Provider attempts are append-oriented.
24. Provider retries occur under the same Delivery.
25. Cross-provider failover is not blindly performed when previous-provider acceptance is indeterminate.
26. Provider SDKs remain behind Notification provider interfaces.
27. Business transactions use transactional outbox rather than direct notification network I/O.
28. Provider callback events are authenticated and deduplicated.
29. Transactional templates are immutable/versioned.
30. Existing Delivery retries use the same rendered logical content/template version.
31. Notification rendering occurs before provider delivery attempts.
32. Recipient/content snapshots follow explicit privacy/retention policy.
33. Broker DLQ state is not product truth; terminal delivery state is durable in Postgres.
34. Customer notifications and platform SRE alerts are separate systems.
35. In-app notifications reuse the same logical Notification domain.
36. Notification content never persists server credentials/secrets.
37. Historical notification/delivery state is not silently rewritten.

---

# 10. JobDefinition / JobRevision / JobRun / Scheduler

## Purpose

Jobs represent durable scheduled invocation of a Project-local backend capability.

A JobDefinition is stable identity. A JobRevision is immutable schedule/execution policy. A JobRun is one logical scheduled occurrence.

The scheduler is infrastructure/orchestration, not the source of truth. PostgreSQL schedule state and JobRun uniqueness are authoritative.

## Binding Refinement

Scheduled/internal work revealed that Binding must support internal-only capability composition.

Binding remains the Project-local composition of OperationVersion + ConnectionRevision + CredentialRevision + exposure/runtime policy, but public exposure is optional.

Initial exposure modes:

- `PUBLIC` — caller-accessible runtime Binding; has an active BindingPublicIdentifier.
- `INTERNAL` — callable only by trusted platform sources such as Jobs/Syncs; has no public runtime identifier.

`QUERY` / `ACTION` remains semantic invocation kind. Exposure mode is a separate axis.

This avoids creating a second composition model for background work and prevents unnecessary public endpoints for scheduled capabilities.

## Ownership and Cardinality

- Workspace `1 -> N JobDefinition`
- Project `1 -> N JobDefinition`
- JobDefinition `1 -> N JobRevision`
- JobDefinition `1 -> N JobRun`
- JobRun `0..1 -> Execution` for the canonical target invocation

JobDefinition belongs to exactly one Workspace and Project.

JobRevision references one stable Binding and, when an occurrence is materialized, JobRun pins the exact BindingRevision selected for that occurrence.

## JobDefinition

Stable identity and mutable lifecycle only.

Expected lifecycle:

- `ACTIVE`
- `PAUSED`
- `ARCHIVED`

Expected fields include identity, Workspace/Project ownership, name, active_revision_id, lifecycle timestamps, and audit metadata.

Pausing prevents creation of new occurrences; it does not silently rewrite or cancel already-created JobRuns.

## JobRevision

Immutable after creation.

Contains schedule and execution semantics such as:

- Binding target
- schedule type/expression
- IANA timezone
- start/end constraints where supported
- misfire policy
- overlap/concurrency policy
- bounded catch-up policy
- optional input mapping for scheduled invocation

Editing any of these creates a new JobRevision and atomically repoints `JobDefinition.active_revision_id` after validation.

Historical JobRuns retain the JobRevision that produced them.

## Schedule Representation

V1 should support at least recurring cron-like schedules with explicit IANA timezone and may support one-time schedules where product UX requires them.

Schedule definition is canonical; `next_due_at` is a mutable scheduling optimization/index, not historical truth.

All persisted occurrence identities use UTC instants.

Timezone-aware calculation must use one canonical scheduling implementation/library so DST semantics are deterministic.

Expected DST semantics:

- nonexistent local time during spring-forward is skipped rather than invented;
- repeated local time during fall-back represents distinct UTC occurrences when the schedule naturally resolves to both instants;
- scheduler behavior is documented and covered by tests.

## Scheduled Occurrence Identity

One logical occurrence is identified by:

`(job_definition_id, scheduled_for)`

with a database uniqueness constraint.

`scheduled_for` is the intended canonical UTC occurrence time, not worker-start time.

Multiple scheduler replicas may race to materialize the same occurrence; exactly one JobRun row wins via the unique constraint.

This is deduplication of logical occurrence, not a claim of exactly-once execution.

## Scheduler HA Model

The scheduler is designed to run with multiple replicas.

It does not rely on a singleton process or leader being permanently healthy.

Typical loop:

1. query due active JobDefinitions/JobRevisions using database time;
2. claim small batches using row locking / `FOR UPDATE SKIP LOCKED` or equivalent;
3. calculate due occurrence(s);
4. transactionally create JobRun(s) guarded by `(job_definition_id, scheduled_for)` uniqueness;
5. create corresponding OutboxEvent(s) in the same transaction;
6. advance `next_due_at` optimization;
7. commit.

If two schedulers race, database constraints determine occurrence creation safely.

## Misfire Policy

Scheduler downtime must have explicit semantics rather than accidental behavior.

V1 policies:

- `SKIP` — do not create missed occurrences; resume from next future occurrence.
- `RUN_ONCE` — collapse one or more missed occurrences into one recovery JobRun.
- `CATCH_UP_BOUNDED` — materialize missed occurrences individually up to a configured/platform-capped maximum.

Unbounded catch-up is forbidden.

The JobRun records the original `scheduled_for` value even when started late.

## Overlap / Concurrency Policy

V1 policies:

- `ALLOW` — multiple JobRuns for different occurrences may execute concurrently.
- `SKIP_IF_RUNNING` — occurrence is durably recorded as `SKIPPED` when an earlier run is still active.
- `SERIALIZE` — occurrences remain durable but execute one at a time in occurrence order, subject to bounded backlog safeguards.

`REPLACE` / force-cancel-previous is not supported initially because cancellation cannot safely undo arbitrary upstream side effects.

Write-heavy jobs should default toward non-overlapping behavior in product UX, while the exact policy remains explicit.

## JobRun

JobRun is one logical scheduled occurrence.

Expected states:

- `PENDING`
- `QUEUED`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `INDETERMINATE`
- `SKIPPED`
- `CANCELLED`
- `DEAD_LETTERED`

Expected durable fields include:

- workspace_id
- project_id
- job_definition_id
- job_revision_id
- scheduled_for
- binding_id
- binding_revision_id
- execution_id nullable until/if created
- lifecycle timestamps
- terminal error summary where applicable

JobRun state is product truth; RabbitMQ message state is not.

## Binding Revision Pinning

At occurrence materialization, the scheduler resolves the JobRevision's stable Binding to the currently active compatible BindingRevision and pins that exact revision into JobRun.

Queue delay or later Binding publication does not change which revision that JobRun executes.

If no executable BindingRevision is available at occurrence creation, the occurrence becomes a durable failed/skipped configuration outcome according to policy rather than silently executing a future revision.

## Execution Relationship

A JobRun creates one logical Execution for its canonical Binding invocation.

Automatic retries are ExecutionAttempts under that Execution, not new JobRuns.

Manual operator replay creates a new Execution and/or explicit replay JobRun semantics; it does not rewrite the historical JobRun.

## Input Snapshot

Scheduled invocation input that derives from JobRevision literals/config is deterministically materialized for the JobRun/Execution.

If future jobs reference dynamic data, the definition must state whether values are snapshotted at occurrence creation or resolved at execution time. V1 should prefer deterministic snapshotting where practical.

## Cancellation

Cancelling a PENDING/QUEUED JobRun prevents execution.

Cancelling a RUNNING JobRun is cooperative and follows Execution cancellation semantics.

Once a mutation may have reached upstream, cancellation must not falsely imply that no side effect occurred; outcome may remain `INDETERMINATE`.

## Notifications

Job domain emits facts such as:

- JobRunFailed
- JobRunDeadLettered
- JobRunIndeterminate

Notification preferences/policies decide whether and how the customer is notified.

Job workers do not send email directly.

## Retention and Scale

JobDefinition/JobRevision are low-volume control state.

JobRun is append/history-oriented and may become high volume for frequent schedules.

JobRun should be designed for time-based retention/partitioning if production volume warrants it, but does not need separate storage initially.

Indexes should support Workspace/Project/JobDefinition + recent time/status queries.

## Frozen Invariants

1. JobDefinition is stable identity; JobRevision is immutable schedule/execution configuration.
2. Jobs belong to exactly one Workspace and Project.
3. Jobs invoke Project-local Binding composition rather than inventing a second execution-composition model.
4. Binding supports `PUBLIC` and `INTERNAL` exposure modes; internal Bindings require no public identifier.
5. JobRun represents one logical scheduled occurrence.
6. `(job_definition_id, scheduled_for)` uniquely identifies a scheduled occurrence.
7. Multiple scheduler replicas are safe; singleton scheduler correctness is not required.
8. PostgreSQL schedule/JobRun state is authoritative; broker state is not.
9. Scheduler creation of JobRun and OutboxEvent is atomic in one DB transaction.
10. `next_due_at` is an optimization, not historical truth.
11. Schedule timezone is explicit and uses IANA identifiers.
12. DST behavior is deterministic and tested.
13. Misfire policy is explicit; unbounded catch-up is forbidden.
14. Overlap policy is explicit; unsafe implicit cancellation/replacement is not supported.
15. JobRun pins exact JobRevision and BindingRevision at occurrence materialization.
16. Later Binding publication cannot change an existing JobRun's executable revision.
17. Automatic retries remain ExecutionAttempts under the JobRun's logical Execution.
18. JobRun product state survives broker/DLQ cleanup.
19. Cancellation cannot claim remote side effects were undone when outcome is ambiguous.
20. Job domain emits notification-worthy facts; it does not perform notification delivery directly.

---

# 11. Transactional Outbox / Dispatcher / Broker Delivery

## Purpose

The transactional outbox provides a durable bridge between authoritative PostgreSQL state and RabbitMQ work/event delivery.

It prevents the dual-write failure window where business state commits but the corresponding broker message is lost.

PostgreSQL is truth. RabbitMQ provides durable at-least-once transport.

## Atomic Producer Pattern

Any business transition requiring asynchronous work/event publication performs, in one PostgreSQL transaction:

1. mutate/create authoritative business state;
2. insert immutable OutboxEvent describing the work/event;
3. commit.

Examples:

- scheduler creates JobRun + `RunJob` OutboxEvent;
- Workspace creates invitation + `WorkspaceInvitationCreated` event;
- Billing applies state + emits entitlement/notification event;
- Sync trigger creates SyncRun + dispatch intent.

No originating domain performs broker network I/O inside its DB transaction.

## OutboxEvent Shape

Expected fields:

- id / stable message_id
- workspace_id nullable only for truly platform-global events
- event_type
- schema_version
- aggregate_type
- aggregate_id
- small payload / durable references
- created_at
- available_at
- status
- lease_id
- lease_expires_at
- publish_attempts
- last_error_code
- published_at

Payloads must remain small. Large bodies/files live in authoritative DB/object storage and messages carry IDs/references.

Secrets/plaintext credentials are forbidden in Outbox payloads.

## Typed Versioned Envelopes

Broker messages are explicit contracts, not arbitrary function/RPC serialization.

Conceptual envelope:

```json
{
  "type": "run_job",
  "version": 1,
  "message_id": "...",
  "created_at": "...",
  "workspace_id": "...",
  "payload": {
    "job_run_id": "..."
  }
}
```

Consumers validate type/version before processing.

Unknown unsupported versions are rejected/dead-lettered safely rather than guessed.

## Work Commands vs Domain Events

The platform distinguishes:

### Work commands

Examples:

- `RUN_JOB`
- `EXECUTE_OPERATION`
- `RUN_SYNC`
- `PROCESS_WEBHOOK`
- `DELIVER_NOTIFICATION`

These request durable processing of a known work item.

### Domain/internal events

Examples:

- `WorkspaceInvitationCreated`
- `CredentialRotated`
- `BindingPublished`
- `JobRunFailed`

These announce facts and may have multiple consumers.

They may use the same broker/outbox infrastructure but their contracts and consumer semantics remain distinct.

## Dispatcher HA Model

Multiple Outbox dispatcher replicas may run concurrently.

Dispatcher claims batches using lease/locking semantics such as `FOR UPDATE SKIP LOCKED`.

Claim state includes `lease_id` and `lease_expires_at` so abandoned rows can be reclaimed.

No permanent singleton dispatcher is required.

## Publish Confirmation

Dispatcher publishes to RabbitMQ durable/quorum queues and waits for publisher confirmation before marking an OutboxEvent as published.

It must not mark an event published before broker confirmation.

However, a failure can still occur after RabbitMQ accepted the message but before PostgreSQL records `published_at`.

In that case the dispatcher republishes later.

Therefore duplicate broker messages are expected and consumers must be idempotent.

This is deliberate at-least-once delivery.

## No Exactly-Once Claim

Transactional outbox removes lost-message dual-write windows but does not provide exactly-once end-to-end processing.

Correctness is achieved through:

- stable message IDs
- domain idempotency/dedupe constraints
- consumer inbox/dedupe where appropriate
- logical Execution/JobRun identities
- provider/upstream idempotency where available

## Consumer Acknowledgement

Consumers acknowledge RabbitMQ messages only after the relevant durable processing boundary has completed.

If a consumer crashes before acknowledgement, the broker may redeliver.

Redelivery must be harmless through domain-specific idempotency.

## Retry / Backoff

Transport retry is bounded and separate from business retry.

RabbitMQ retry/dead-letter topology may delay transient failures, but the authoritative domain record tracks attempts/terminal outcome where product visibility matters.

A broker message must not retry beyond a domain deadline such as Notification `expires_at`.

Business operation retries (for example upstream API retry) remain ExecutionAttempt semantics, not broker-redelivery semantics.

## Dead Lettering

RabbitMQ DLQ is transport state only.

Before/when work is terminally dead-lettered, relevant product state is persisted, for example:

- JobRun `DEAD_LETTERED`
- Execution `DEAD_LETTERED`
- NotificationDelivery `FAILED` / `EXPIRED`
- WebhookDelivery terminal state

Operations dashboard must not depend on RabbitMQ management history to explain customer work.

## Ordering

No global event ordering guarantee is assumed.

Where a domain requires ordering, it must encode a domain-specific sequence/version and reject or defer stale/out-of-order transitions safely.

The platform does not serialize all tenants/work through one global queue merely to manufacture ordering.

## Consumer Inbox / Dedupe

A generic Inbox table may be used for consumers whose semantics require "process this message ID once" and do not already have a stronger domain uniqueness key.

Inbox is not mandatory for every message.

Prefer domain-native constraints when stronger:

- JobRun unique occurrence
- Action IdempotencyRecord
- provider webhook event ID
- Notification dedupe key
- UsageEvent dedupe key

## Outbox Retention

Successfully published/reconciled OutboxEvents are operational reliability history, not permanent business records.

They may be purged/archived after a bounded retention period once authoritative domain/audit state exists elsewhere.

Failed/unpublished events require longer retention/alerting until resolved.

Outbox table should support efficient queries by status/available_at and eventual partitioning/purge if volume requires it.

## Queue Topology

Avoid one queue per tenant or event type.

Initial bounded queue groups may include:

- execution/jobs
- sync
- webhook
- notifications
- maintenance
- dead-letter flows

Exact topology is operational configuration and may evolve without changing domain contracts.

Durable production queues use replicated/durable broker semantics; local development may use a simpler single-node broker while preserving contracts.

## Outbox / Broker Invariants

1. PostgreSQL business state is authoritative; RabbitMQ is transport.
2. Any DB state transition requiring async publication inserts OutboxEvent in the same transaction.
3. Domains do not perform broker network I/O inside business DB transactions.
4. Outbox messages are typed and schema-versioned.
5. Payloads are small references; secrets and large blobs are forbidden.
6. Multiple dispatcher replicas are safe.
7. Dispatcher uses leases/locking and supports stale-claim recovery.
8. An event is marked published only after broker publisher confirmation.
9. Publish-confirm/DB-update ambiguity may cause duplicate messages and is accepted.
10. Consumers therefore operate at-least-once and must be idempotent.
11. Broker acknowledgement occurs only after the consumer's durable processing boundary.
12. Broker retry is separate from business-operation retry.
13. Domain deadlines override transport retry.
14. RabbitMQ DLQ is not product truth.
15. Customer-visible dead-letter/failure state is persisted in domain tables.
16. No global ordering guarantee exists; domains requiring ordering encode it explicitly.
17. Generic Inbox dedupe is used only where stronger domain constraints do not already exist.
18. Successfully reconciled outbox rows may be purged after bounded retention.
19. Queue topology is bounded and shared, not one queue per tenant.
20. The architecture makes no exactly-once processing claim.


---

# WebhookEndpoint / WebhookEndpointRevision / WebhookDelivery

## Purpose

WebhookEndpoint is the stable Project-scoped ingress identity for authenticated external events.

WebhookEndpointRevision is immutable ingress/verification configuration.

WebhookDelivery is one logical accepted provider event.

Webhook-triggered business work is executed through the canonical Binding/Execution pipeline.

## Ownership

WebhookEndpoint belongs to exactly one Workspace and one Project.

One Project may have many WebhookEndpoints.

Endpoint Workspace/Project ownership is immutable in ordinary operation.

## Aggregate Shape

```text
Project
└── WebhookEndpoint
      ├── WebhookEndpointRevision
      ├── WebhookEndpointSecretVersion
      ├── WebhookPublicIdentifier
      └── WebhookDelivery
            └── Execution
                  └── ExecutionAttempt
```

## Endpoint Lifecycle

Expected lifecycle:

- `DRAFT` before first valid publication where needed
- `ACTIVE`
- `DISABLED`
- `ARCHIVED`

`DISABLED` immediately rejects new ingress.

Already accepted Deliveries remain the platform's responsibility.

## Public Ingress Identifier

Webhook public IDs are routing identifiers, not authentication secrets.

Public IDs are independently rotatable/revocable through historical `WebhookPublicIdentifier` records.

## WebhookEndpointRevision

EndpointRevision is immutable and pins ingress semantics such as:

- target Binding identity
- verification scheme/configuration
- event-ID extraction policy
- signed timestamp/replay policy
- accepted content types
- request-size limits
- event-type filters
- payload-to-Binding mapping
- provider ACK behavior
- payload-retention policy

Publication atomically switches `WebhookEndpoint.active_revision_id`.

## Target Binding

WebhookEndpointRevision targets a stable internal Binding.

At durable acceptance time, the then-active BindingRevision is resolved once and pinned onto WebhookDelivery.

Later Binding publishes do not mutate an already accepted Delivery.

Webhook execution therefore reuses the canonical compiled Binding/Execution engine rather than introducing a second executor.

## Verification Boundary

Webhook authenticity is verified before normal WebhookDelivery creation.

Signature schemes that sign raw bytes must verify against the exact bounded raw request body, not parsed/re-serialized JSON.

Ingress pipeline conceptually:

```text
resolve endpoint
→ enforce gross size/header/content limits
→ capture/stream bounded raw body
→ verify authenticity
→ enforce timestamp/replay checks where supported
→ extract event identity
→ durably accept Delivery + Outbox
```

## Verification Schemes

Verification schemes come from a typed registry.

Initial supported categories may include:

- `NONE` for explicitly allowed cases only
- `STATIC_TOKEN`
- `HMAC_SHA256`
- `PROVIDER_NATIVE`

Possible later schemes include asymmetric signatures/JWT.

Known-provider adapters own provider-specific header/signature/timestamp semantics.

## Verification Secrets

Inbound webhook verification secrets are not outbound Credentials.

They use a dedicated `WebhookEndpointSecretVersion` family while reusing the same encryption/KMS principles:

- envelope encryption
- write-only customer semantics
- immutable secret versions
- active/retiring rotation overlap where provider semantics require it
- revocation/destruction lifecycle
- strict redaction

Only bounded active/retiring versions may participate in verification.

## Replay Protection

When provider signatures include timestamps, EndpointRevision may enforce provider-appropriate maximum skew/age.

Timestamp-window replay protection complements but does not replace logical event dedupe.

## Provider Event Identity

Stable provider event IDs are the preferred dedupe key.

Expected uniqueness:

`UNIQUE(webhook_endpoint_id, provider_event_id)`

Dedupe scopes to stable Endpoint identity, not EndpointRevision, so provider retries remain duplicates across later config publishes.

## Duplicate Payload Integrity

Same provider event ID + same payload hash is a normal duplicate retry.

Same provider event ID + different payload hash is a security/integration anomaly and is not silently accepted as a normal duplicate.

## Providers Without Stable Event IDs

When no provider-stable event ID exists, dedupe may use a documented best-effort derived key from payload hash and other bounded provider metadata/time window.

Such dedupe is explicitly weaker and must not be described as equivalent to provider event-ID dedupe.

## Trusted Acceptance Boundary

Unknown endpoints, oversized requests, invalid signatures, expired signed timestamps, malformed framing, and similar untrusted ingress do not normally create customer WebhookDelivery rows.

They belong to security/operational telemetry and sampled diagnostics.

WebhookDelivery is created only after authenticity/admission checks have succeeded sufficiently to accept platform responsibility.

## Durable ACK Contract

Provider success is returned only after durable acceptance.

Correct flow:

```text
verify/authenticate request

BEGIN
  insert WebhookDelivery
  insert OutboxEvent(PROCESS_WEBHOOK)
COMMIT

return provider success ACK
```

If the durable commit fails, return a retryable failure response according to provider semantics.

A success ACK means **durably accepted responsibility**, not that downstream business processing has completed.

## Async Processing

V1 webhook triggers are asynchronous events.

Business execution is not performed before the provider ACK by default.

Flow:

```text
Provider request
→ verify
→ Delivery + Outbox commit
→ provider ACK
→ outbox dispatcher
→ RabbitMQ
→ webhook worker
→ Execution(source=WEBHOOK)
→ canonical execution engine
```

Synchronous arbitrary request/response HTTP functions are a distinct future capability and are not hidden inside Webhook semantics.

## WebhookDelivery

WebhookDelivery is one logical accepted provider event.

Expected durable dimensions include:

- `workspace_id`
- `project_id`
- `webhook_endpoint_id`
- `webhook_endpoint_revision_id`
- provider event ID where available
- provider event type where available
- payload hash/size/content type
- pinned Binding ID/BindingRevision ID
- lifecycle status
- accepted/processed timestamps
- normalized terminal error metadata

## Delivery Lifecycle

Expected states:

- `ACCEPTED`
- `PROCESSING`
- `SUCCEEDED`
- `FAILED`
- `IGNORED`
- `DEAD_LETTERED`

Verification failure is not a WebhookDelivery state because an invalid request was never accepted as a legitimate Delivery.

## Event Filters

EndpointRevision may declare accepted/interesting event types.

A legitimate signed provider event that is intentionally irrelevant should generally be ACKed and may be recorded as `IGNORED` when customer observability benefits from it, rather than causing endless provider retries.

Provider-specific ACK semantics remain adapter-owned.

## Payload to Binding Mapping

EndpointRevision defines declarative mapping from provider event data to Binding caller inputs.

No arbitrary JavaScript is required initially.

Publication validates that required Binding inputs are satisfied by allowed mapped sources.

## Execution Relationship

Webhook worker creates one original logical Execution for an accepted Delivery.

`Execution.webhook_delivery_id` is a real FK.

Duplicate broker delivery must not create another original logical Execution.

A strong domain uniqueness rule should enforce one original execution per Delivery.

Manual replay creates a new Execution linked through replay lineage while retaining the same original WebhookDelivery.

## Provider Retries vs Internal Retries

Provider retries of the same event are handled through WebhookDelivery dedupe.

Internal business-operation retries are ExecutionAttempts under one Execution.

These are separate retry dimensions.

## Duplicate Request Handling

For a legitimate duplicate request:

1. verify authenticity
2. locate existing Delivery by event identity
3. verify payload hash compatibility
4. return normal provider success
5. do not insert another Delivery
6. do not enqueue another original execution

Concurrent duplicate arrivals rely on database uniqueness for correctness; no distributed lock is required.

## Payload Storage

Accepted webhook processing needs durable payload material after the provider request returns.

WebhookDelivery stores bounded metadata plus a payload reference/hash.

Small payloads may initially live in Postgres. Large payloads should be able to use object-storage references without changing domain semantics.

Raw and parsed/normalized payload representations remain conceptually distinct.

## Payload and Header Retention

Raw payload, sanitized payload, Delivery metadata, and dedupe identity may have different retention periods.

Dedupe identity must live at least as long as the provider's meaningful retry horizon.

Payload content may expire much earlier.

Arbitrary inbound headers are not retained. Sensitive headers/tokens/signatures are redacted or omitted.

## Security / Abuse Protection

Before expensive verification/storage, ingress enforces bounded:

- request body size
- request rate
- connection/request timeout
- header count/size
- supported content type

Provider IP allowlists may supplement cryptographic verification but do not replace it.

Long-lived webhook secrets should not be placed in URL paths unless provider constraints force it; if unavoidable, logging/redaction must protect them.

## Dead-Letter State

RabbitMQ DLQ is transport state, not product truth.

If internal processing exhausts durable retry policy, WebhookDelivery records `DEAD_LETTERED` or another explicit terminal product state.

Customer operations can therefore distinguish:

- provider event never accepted
- provider event accepted but internal processing failed

## Manual Replay

Manual replay creates a new Execution, not a new WebhookDelivery.

Replay defaults to the original pinned BindingRevision for reproducibility while resolving currently valid Credential secret material.

Historical revoked secrets are never resurrected.

## Disable Semantics

Disabling a WebhookEndpoint rejects new incoming events.

It does not discard or cancel Deliveries already durably accepted.

## Health

Endpoint operational health is separate from lifecycle.

Possible observations include:

- healthy
- no recent events
- signature-failure spike
- processing backlog
- config error

A few bad requests do not automatically mutate Endpoint lifecycle.

## Scalability

WebhookDelivery is append-heavy and should remain time-partitionable.

Likely operational indexes include Workspace/Project/Endpoint + received time, Endpoint + provider event ID, and status + received time.

Every inbound retry request does not need its own durable attempt row; duplicate-request volume may be captured in counters/telemetry instead.

## Frozen Invariants

1. WebhookEndpoint belongs to exactly one Project and Workspace.
2. Endpoint is stable ingress identity; WebhookEndpointRevision is immutable configuration.
3. Public webhook IDs are routing identifiers, not authentication secrets.
4. Public webhook identifiers are independently rotatable/revocable.
5. Endpoint lifecycle contains an immediate ingress kill switch.
6. Endpoint verification configuration is revisioned.
7. Verification uses exact raw request bytes where provider signatures require them.
8. Verification secrets use encrypted, versioned secret storage and are not outbound Credentials.
9. Verification-secret rotation may support bounded active/retiring overlap.
10. Signed timestamps are checked where provider semantics support replay windows.
11. Stable provider event IDs are the preferred dedupe identity.
12. Dedupe is scoped to stable Endpoint identity, not EndpointRevision.
13. Same provider event ID plus same payload hash is a duplicate retry.
14. Same provider event ID plus different payload hash is a security/integration anomaly.
15. Providers without event IDs receive documented best-effort payload-based dedupe only.
16. Untrusted/invalid ingress does not create normal WebhookDelivery rows.
17. WebhookDelivery is created only after authenticity/admission checks succeed sufficiently.
18. Provider success ACK is returned only after Delivery + Outbox intent commit durably.
19. Provider ACK means durably accepted responsibility, not completed business processing.
20. Default webhook processing is asynchronous.
21. Network/business execution does not happen inside the ingress persistence transaction.
22. EndpointRevision targets the canonical Binding/Execution system rather than owning a separate executor.
23. WebhookDelivery pins the BindingRevision selected at durable acceptance.
24. Later Binding publishes do not alter an accepted Delivery.
25. Provider duplicate requests cannot create duplicate logical Deliveries.
26. Concurrent duplicate arrival relies on database uniqueness for correctness.
27. Duplicate accepted events return provider success without re-enqueueing original work.
28. One accepted Delivery normally creates one original logical Execution.
29. Worker redelivery cannot create duplicate original Executions.
30. Provider retries and internal Execution retries are separate concepts.
31. Raw webhook payload storage is bounded and retention-controlled.
32. Large payloads may use object-storage references rather than bloating Postgres.
33. Payload content and dedupe metadata have independent retention.
34. Arbitrary inbound headers are not retained.
35. Payload-to-Binding mapping is declarative and validated at publication.
36. Event-type filtering is explicit.
37. Legitimate unwanted provider event types should generally be acknowledged rather than inducing endless provider retries.
38. Product-visible webhook failure/dead-letter state is durable independently of RabbitMQ.
39. Manual replay creates a new Execution, not a new WebhookDelivery.
40. Replay does not resurrect revoked historical Credential secrets.
41. Disabling Endpoint rejects new ingress but does not discard already accepted Deliveries.
42. Provider IP allowlisting supplements but does not replace cryptographic verification.
43. Long-lived webhook secrets should not be placed in URLs unless provider constraints require it.
44. Endpoint health is operational state distinct from lifecycle.
45. WebhookDelivery is designed to be append-heavy/time-partitionable.
46. Dedupe retention lasts at least as long as the provider's meaningful retry horizon.

---

# Sync Architecture Refinement: Provider-Neutral Engine

## Architectural Boundary

The synchronization engine is provider-neutral and capability-driven.

Framer CMS is the first-class V1 adapter and primary product UX specialization, but it is not the architectural boundary of the engine.

The generic Sync engine owns stable object identity, mappings, reconciliation, full vs incremental scans, checkpoints, projection hashes, conflict handling, delete semantics, mark-and-sweep reconciliation, dry-run/apply, destructive-change guards, run/item lifecycle, resumability, idempotency interaction, scheduling integration, and observability.

Provider-specific behavior belongs behind source/target adapter capabilities.

## Adapter Model

Conceptually:

```text
SourceAdapter
- discover_schema
- validate_config
- read_page
- read_incremental
- checkpoint capability
- tombstone capability
- canonical identity extraction
```

```text
TargetAdapter
- discover_schema
- validate_config
- create
- update
- upsert
- delete
- soft-delete/archive/draft where supported
- deterministic identity capability
- publication/deployment capability
```

Capabilities are explicit and validated when a SyncRevision is published. The engine must never assume all targets support identical semantics.

## Framer as V1 Adapter

Framer-specific concepts such as Managed Collections, stable CMS field IDs, user-editable fields, Framer item IDs, draft behavior, and publish/deploy remain inside the Framer adapter/configuration layer rather than leaking into generic Sync tables.

Core Sync tables use provider-neutral concepts such as source identity hash, target identity, target namespace/type, adapter metadata, schema fingerprints, and capability flags.

## Binding Integration

When either side is backed by an external API operation, Sync reuses INTERNAL Bindings and the canonical execution engine.

```text
external API source
    -> INTERNAL QUERY Binding
    -> canonical source records
    -> Sync engine
```

```text
Sync engine
    -> INTERNAL ACTION Binding
    -> external API target
```

Sync must not implement a second generic HTTP execution stack.

## Stable Identity and Mapping

Every SyncRevision requires a stable source identity strategy. Array position, row order, and display titles are not stable identities. Composite identities are supported conceptually.

SyncMapping is durable application state. Generic SyncMapping fields must not be named after Framer-specific entities.

Core uniqueness remains equivalent to:

`UNIQUE(sync_definition_id, source_identity_hash)`

and, where the target adapter declares exclusive identity semantics:

`UNIQUE(sync_definition_id, target_identity)`

## Capability-Driven Missing/Delete Behavior

Generic missing-target actions are capability-driven. Core intent may include KEEP, DELETE, SOFT_DELETE, ARCHIVE, or a typed target-specific lifecycle action.

Framer MARK_DRAFT is an adapter-specific realization, not a universal Sync-core lifecycle value.

## Schema and Typed Mapping

Adapters expose discoverable schemas where possible. SyncRevision records relevant schema fingerprints and typed mappings. Incompatible schema drift blocks APPLY before mutations begin.

The generic mapping model supports typed values and declarative transforms; arbitrary user code/eval is outside V1.

## Framer Managed Collections

For external-to-Framer sync, Managed Collections are the recommended mode because stable item identity and upsert semantics allow substantially safer retries and reconciliation.

Existing/unmanaged Framer collections remain supported as an advanced mode with explicitly weaker create/reconciliation guarantees.

## Scheduling

Scheduled Syncs reuse JobDefinition / JobRun. Sync does not own a separate scheduler.

JobDefinition may target a SyncDefinition through a real FK/XOR-constrained target model rather than a polymorphic unvalidated ID.

## Product Scope

The internal engine is generic, but V1 product UX remains opinionated around Framer synchronization.

The abstraction is an implementation boundary and future-optionality decision, not a commitment to expose a generic ETL/workflow builder.

## Additional Frozen Invariants

1. Sync core is provider-neutral and capability-driven.
2. Framer CMS is the first-class V1 adapter/UX specialization, not the engine boundary.
3. Provider-specific behavior is implemented behind typed source/target adapters.
4. Adapter capabilities are explicit and validated at SyncRevision publication.
5. Generic Sync tables do not contain Framer-specific identity columns.
6. External API sides reuse INTERNAL Bindings and canonical Execution semantics.
7. Stable source identity is mandatory and provider-independent.
8. SyncMapping remains durable provider-neutral application state.
9. Missing/delete behavior is expressed through generic intent plus adapter capabilities.
10. Schema discovery, typed mapping, reconciliation, checkpointing, and destructive-change protection belong to the generic core.
11. Framer Managed Collections are a specialization that provides stronger deterministic identity guarantees.
12. Existing Framer Collections are supported with weaker guarantees that are surfaced explicitly in UX.
13. Scheduled Syncs reuse the shared Job scheduler.
14. Generic engine optionality must not turn V1 into a generic ETL/workflow product.


---

# AuditEvent

## Purpose

AuditEvent is the immutable security/accountability ledger for material control-plane and operator actions.

Audit is distinct from:

- Execution history
- application logs
- traces/metrics
- security telemetry
- business-domain event streams
- notification history

Audit answers:

- who performed a material action
- in which Workspace/Project context
- through which product surface
- what resource was affected
- what changed
- whether the action succeeded
- whether privileged/support access was involved
- which request/session/correlation identifiers can be used for investigation

AuditEvent is not used as the source of truth for current business state.

## Scope

AuditEvent is created for material actions such as:

- Workspace creation/update/archive
- membership role changes
- invitation creation/revocation
- Project create/suspend/archive/transfer
- Framer project linking/unlinking
- Connection create/update/disable/archive
- Credential create/rotation/revocation/destruction
- Operation/Binding/Sync/Job/Webhook publication
- runtime capability disable/enable
- entitlement/manual grant changes
- billing-administration changes
- public identifier rotation/revocation
- destructive sync confirmation
- manual replay/retry actions
- mapping relink/detach
- notification preference changes
- support/admin impersonation or privileged access
- secret access/decrypt control-plane operations where such access is ever permitted
- data export/purge requests
- security-sensitive settings changes

Routine high-volume runtime activity does not create AuditEvent rows.

Examples that belong elsewhere:

- every Query execution
- every webhook attempt
- every queue retry
- every cache hit
- every metric sample

## Ownership

Every tenant-scoped AuditEvent carries `workspace_id`.

`project_id` is nullable and present when the action is attributable to one Project.

Platform-level internal events may have no Workspace only when explicitly marked as platform-scope.

Tenant-scoped actions must never lose their Workspace attribution even if the affected resource is later deleted/archived.

## Actor Model

AuditEvent records a normalized actor.

Initial actor types:

- `USER`
- `SERVICE`
- `SYSTEM`
- `SUPPORT`

Expected actor fields:

- `actor_type`
- `actor_user_id` nullable
- `actor_service_key` nullable
- `actor_display_snapshot` nullable
- `actor_workspace_role_snapshot` nullable

The actor snapshot is informational; authorization truth remains in the relevant domain state.

## Effective Actor vs Original Actor

Privileged support/admin access requires dual attribution.

Audit must distinguish:

- original authenticated actor
- effective actor/context used for the action

For example:

```text
OpenAI/Platform Support User A
    -> assumes support session for Workspace X
    -> disables Credential Y
```

The event records both the real support identity and the effective tenant context.

Impersonation must never make an event appear as though the customer user performed the action.

## Support Access

Support/privileged access is itself auditable.

Support sessions should have:

- support session ID
- reason/ticket reference where available
- started_at
- expires_at
- original support actor
- target Workspace/User context
- permitted scope

Material actions taken during that session reference the support session.

Break-glass access, if later introduced, requires an explicit elevated audit action and reason.

## Subject / Resource Identity

AuditEvent records one primary affected resource using typed resource identity.

Expected fields:

- `resource_type`
- `resource_id`
- optional `resource_display_snapshot`

Examples:

- `WORKSPACE`
- `PROJECT`
- `CONNECTION`
- `CREDENTIAL`
- `OPERATION`
- `BINDING`
- `SYNC_DEFINITION`
- `JOB_DEFINITION`
- `WEBHOOK_ENDPOINT`
- `ENTITLEMENT_GRANT`

Generic resource identity is acceptable for audit because AuditEvent is historical observational data rather than a transactional FK-enforced aggregate relationship.

Where useful, dedicated nullable foreign keys may still be included for high-value tenant roots such as Workspace/Project/User.

Audit must remain readable even after resource archival/purge, so display/name snapshots may be retained.

## Action Identity

Actions use stable typed action keys rather than free-form prose.

Examples:

- `workspace.created`
- `membership.role_changed`
- `project.suspended`
- `connection.disabled`
- `credential.secret_rotated`
- `binding.published`
- `binding.public_id_rotated`
- `job.paused`
- `webhook.secret_rotated`
- `sync.delete_guard_confirmed`
- `sync.mapping_relinked`
- `execution.replayed`
- `support.session_started`

Action keys are versioned semantically through registry discipline, not per-row schema versions.

## Outcome

AuditEvent records outcome:

- `SUCCEEDED`
- `FAILED`
- `DENIED`

`FAILED` means the actor was authorized enough to attempt the operation, but the material operation did not complete.

`DENIED` records security-relevant authorization/policy denials when worth preserving.

Not every malformed or abusive request becomes AuditEvent; high-volume ingress rejection belongs to security telemetry.

## Change Representation

Audit stores a sanitized structured change summary.

Preferred representation:

- `before_json` nullable
- `after_json` nullable
- `change_json` / JSON Patch-like normalized diff nullable

Audit payloads contain only fields appropriate for long-lived accountability.

They must never contain:

- plaintext credentials
- Authorization headers
- session tokens
- refresh/access tokens
- signing secrets
- password/reset secrets
- raw KMS-encrypted secret ciphertext unless explicitly necessary
- full arbitrary webhook/runtime payloads

Secret-related audit events record metadata such as:

- Credential ID
- SecretVersion ID
- rotation/revocation reason
- actor
- timestamp

not the secret itself.

## Sensitive / PII Fields

Audit should minimize PII.

Where identity is relevant, retain only what is necessary for accountability, such as:

- user ID
- email snapshot where operationally/legal useful
- IP address subject to retention policy
- user-agent summary where useful

IP/user-agent retention may be shorter than core audit metadata.

Sensitive values in before/after diffs are represented as:

- redacted marker
- changed/not-changed indication
- safe fingerprint where justified

## Request / Surface Context

AuditEvent may record:

- `request_id`
- `trace_id`
- `session_id`
- `support_session_id`
- `surface`
- `ip_address` / hashed or truncated form according to policy
- `user_agent_summary`

Initial surface values may include:

- `WEB_DASHBOARD`
- `FRAMER_PLUGIN`
- `PUBLIC_API`
- `INTERNAL_API`
- `PLATFORM_OPS`
- `SYSTEM_WORKER`

This allows investigations to distinguish customer UI actions from internal/operator activity.

## Correlation

AuditEvent can reference relevant business/runtime IDs for investigation, for example:

- source Execution ID
- replayed Execution ID
- JobRun ID
- SyncRun ID
- WebhookDelivery ID

These are optional correlation fields, not ownership relationships.

Audit does not duplicate full histories from those domains.

## Creation Semantics

For material business mutations, AuditEvent should be persisted transactionally with the state change whenever practical.

Example:

```text
BEGIN
  update Credential lifecycle
  insert AuditEvent
COMMIT
```

This prevents successful control-plane changes from lacking audit history.

Where the action spans an external system and cannot be one DB transaction, audit records the observed outcome and correlation IDs after each durable stage as appropriate.

Audit creation must not depend on an asynchronous logging pipeline for correctness.

## Failed / Denied Actions

Successful mutations are normally recorded transactionally.

Security-sensitive denied actions may be recorded separately after authorization evaluation.

Routine validation errors are not automatically audit-worthy.

The audit registry/policy decides which failed/denied actions are material enough to retain.

## Append-Only Semantics

AuditEvent is append-only.

Rows are never updated to rewrite history.

If an event needs correction or annotation, append a new corrective event referencing the original event.

No normal application code may delete individual AuditEvents.

Retention/purge is policy-driven and performed by dedicated archival/compliance processes.

## Ordering

AuditEvent uses UUIDv7 primary identity and a trusted server timestamp.

No global total-order guarantee is claimed across distributed processes.

Within one database transaction, created events preserve transactional causality.

Consumers/investigators use:

- created_at
- UUIDv7 ordering
- request/correlation IDs
- domain version/revision IDs

for reconstruction.

## Tamper Evidence

PostgreSQL authorization and append-only application semantics are the primary protection.

The schema should support future tamper-evidence such as:

- batch hashes
- exported signed audit archives
- immutable object-storage snapshots

A per-row global hash chain is not required in V1 because it creates unnecessary serialization/correctness complexity.

If regulatory requirements later demand cryptographic tamper evidence, it should be added as an archival/export layer rather than making all product writes depend on a global chain.

## Retention

Audit retention is independent from:

- Execution retention
- payload retention
- notification retention
- webhook retention

Audit metadata is expected to have relatively long retention.

Exact retention duration is entitlement/legal-policy dependent and intentionally deferred.

Resource name/display snapshots may outlive the current resource row where required for historical readability.

Secrets and excessive PII never gain longer retention merely because they appear in audit context.

## Export

Workspace administrators/owners may eventually export tenant audit history subject to entitlements/authorization.

Internal platform/support events must be filtered so tenant exports do not expose unrelated internal identities or security-sensitive platform information.

Exports are generated from immutable AuditEvent data, not application logs.

## Scalability

Audit is append-heavy but far lower volume than Execution.

No initial partitioning is strictly required, but the table is designed to support time-based partitioning if volume or retention requires it.

Expected indexes include:

- `(workspace_id, created_at DESC)`
- `(workspace_id, project_id, created_at DESC)`
- `(workspace_id, actor_user_id, created_at DESC)`
- `(workspace_id, resource_type, resource_id, created_at DESC)`
- `(workspace_id, action, created_at DESC)`
- `request_id`
- `trace_id`
- `support_session_id`

Index count should remain conservative because AuditEvent is write-heavy and query patterns are known.

## Database Shape

Conceptual fields:

```text
audit_events
------------
id UUIDv7 PK

workspace_id nullable only for platform-scope events
project_id nullable

scope                 TENANT | PLATFORM

actor_type
actor_user_id nullable
actor_service_key nullable
actor_display_snapshot nullable
actor_role_snapshot nullable

effective_user_id nullable
support_session_id nullable

action
outcome

resource_type
resource_id nullable
resource_display_snapshot nullable

before_json nullable
after_json nullable
change_json nullable

request_id nullable
trace_id nullable
session_id nullable

surface

ip_address nullable / privacy-controlled
user_agent_summary nullable

metadata_json

created_at
```

Tenant-scope CHECK:

- `scope = TENANT` requires `workspace_id IS NOT NULL`

Platform-scope events may omit workspace_id.

## Frozen Invariants

1. AuditEvent is an immutable accountability ledger, not the current business-state source of truth.
2. Audit is separate from runtime execution history, logs, traces, metrics, notifications, and domain event transport.
3. Material control-plane/security/operator actions create AuditEvents.
4. Routine high-volume runtime operations do not create AuditEvents.
5. Tenant-scoped AuditEvents always retain Workspace attribution.
6. Project attribution is recorded where applicable.
7. Actor identity is normalized and typed.
8. Support/impersonation actions retain both original privileged actor and effective tenant context.
9. Impersonation never makes a support action appear to have been performed by the customer.
10. Support session creation/use is itself auditable.
11. Actions use stable typed action keys.
12. Audit outcome distinguishes SUCCEEDED, FAILED, and DENIED where meaningful.
13. Resource identity is retained even after resource archival/deletion.
14. Before/after/change data is sanitized for long-lived retention.
15. Plaintext credentials/tokens/secrets are never written to audit.
16. Secret-related audit records refer to SecretVersion IDs/metadata, not secret values.
17. PII is minimized and follows separate privacy retention where applicable.
18. Product surface/request/correlation context is recorded where useful.
19. Successful material mutations persist audit in the same DB transaction whenever practical.
20. Audit correctness does not depend on asynchronous log shipping.
21. AuditEvent is append-only.
22. Corrections are new events referencing prior events, not row mutation.
23. Individual AuditEvents are not normally deleted by application code.
24. Retention/purge is centralized policy.
25. No global distributed total-order guarantee is claimed.
26. A global cryptographic hash chain is not required in V1.
27. The design permits later signed archival/tamper-evidence mechanisms.
28. Audit retention is independent from execution/payload retention.
29. Tenant audit export is authorization-filtered and does not leak unrelated internal platform data.
30. AuditEvent is designed to be time-partitionable if scale/retention later requires it.
