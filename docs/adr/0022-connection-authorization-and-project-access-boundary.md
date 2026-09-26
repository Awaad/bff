# ADR 0022: Connection authorization and Project-access boundary

**Status:** Accepted  
**Date:** 2026-09-24

## Context

The Workspace and Project control-plane establish authenticated internal
Users, durable AuthSessions, active WorkspaceMembership authorization, explicit
role permissions, existence hiding, and transactional audited creation.

Connection is the next Phase 1 domain. A Connection represents one logical
external system, account, or environment boundary. It belongs to a Workspace,
may be usable by more than one Project, and is the parent of later Credentials
and Operations.

Several accepted decisions already constrain this domain:

- ADR 0002 requires immutable `ConnectionRevision` records and exact revision
  pinning by published `BindingRevision` records;
- ADR 0010 requires generic and provider-native integrations to use the canonical
  execution engine and central transport protections;
- ADR 0012 separates encrypted Credential secrets from Connection configuration;
- ADRs 0020 and 0021 make internal Users plus active WorkspaceMembership rows the
  control-plane authorization source of truth.

The V2.1 schema already provides `connections`, `connection_drafts`,
`connection_revisions`, and `connection_project_access`. It does not settle the
role permissions, lifecycle transitions, Project-access mutation semantics,
existence-hiding behavior, or transaction boundaries required by the first
Connection API.

These decisions affect the control API, database ACLs, publication, audit, and
later runtime admission. They therefore require one explicit boundary rather
than independent router or repository conventions.

## Decision

### Authorization source of truth

The Connection control plane is authorized through the canonical internal User
and an active WorkspaceMembership:

```text
authenticated users.id
    -> active workspace_memberships row
    -> Workspace role
    -> Connection permission policy
```

No WorkOS organization, role, or permission claim grants Connection access.
Project access to a Connection is product authorization state; it is not inferred
from Framer identity or from a caller-supplied Project identifier.

Connection policy is enforced by the Connection domain service, not only by HTTP
routers. Repository reads remain constrained by `user_id`, `workspace_id`, and an
active WorkspaceMembership. Mutations authorize against transaction-scoped
Workspace, membership, and Connection state.

### Initial permissions

Roles remain explicit permission bundles rather than an ordering comparison.

| Permission | OWNER | ADMIN | BUILDER | VIEWER |
| --- | :---: | :---: | :---: | :---: |
| `connection:read` | yes | yes | yes | yes |
| `connection:create` | yes | yes | yes | no |
| `connection:author` | yes | yes | yes | no |
| `connection:publish` | yes | yes | yes | no |
| `connection:assign_projects` | yes | yes | yes | no |
| `connection:manage_workspace_access` | yes | yes | no | no |
| `connection:manage_lifecycle` | yes | yes | no | no |

`connection:read` covers Connection identity, access mode, lifecycle, provider
identity, and revision metadata. Initial list and detail responses do not expose
mutable draft configuration or full revision configuration.

`connection:author` covers Connection display-name changes, reading and writing
non-secret draft configuration, and reading full published revision
configuration.
`connection:publish` creates an immutable ConnectionRevision.
`connection:assign_projects` replaces the selected-Project set while a Connection
uses `SELECTED_PROJECTS`. `connection:manage_workspace_access` changes the access
mode between `SELECTED_PROJECTS` and `WORKSPACE`.

OWNER and ADMIN alone may disable, re-enable, or archive a Connection because
those operations affect every Project using the Workspace-owned resource.
They also control Workspace-wide Connection access because it automatically
includes current and future Projects. BUILDER remains able to create, configure,
publish, and assign Connections to explicitly selected Projects for the
product-authoring workflow without receiving membership, Workspace-wide access,
or global lifecycle administration authority.

Permission is evaluated before Workspace or Connection lifecycle for an active
member. A role without a requested permission therefore receives the same denial
across lifecycle states it is allowed to address.

### Stable identity and provider identity

A Connection belongs to exactly one Workspace. `workspace_id` is immutable during
ordinary lifecycle.

`provider_key` identifies the typed provider contract and is also immutable. A
change from generic HTTP to a provider-native integration, or between provider
families, creates a new Connection identity rather than changing the meaning of
an existing Connection and its historical revisions.

The provider registry owns:

- recognized provider keys;
- versioned configuration schemas;
- canonicalization and validation;
- compatible Credential schemes and provider capabilities;
- compilation into the canonical execution representation.

The first implementation may register only the generic HTTP provider. Unknown
provider keys are rejected; arbitrary strings are not persisted for later
interpretation.

Connection configuration never contains Credential plaintext, encrypted secret
material, or auth-injection values. Those belong to the Credential domain.

Connection names are trimmed, non-empty, and limited to 120 characters. Names
are not unique within a Workspace because Connection identity, not display name,
is the stable reference.

### Lifecycle and publication

Connection lifecycle is:

```text
DRAFT -> ACTIVE <-> DISABLED -> ARCHIVED
DRAFT -----------------------> ARCHIVED
```

Creation establishes a stable `DRAFT` Connection identity and its access policy.
It does not create an empty or placeholder ConnectionRevision.

Draft configuration is mutable authoring state in `connection_drafts`. Draft
writes pass through the provider's typed validation and canonicalization before
storage so arbitrary or secret-bearing fields cannot use the draft as an
untyped persistence surface. Publishing revalidates a valid draft:

1. validates it through the provider registry;
2. canonicalizes the configuration;
3. allocates the next monotonic revision number while locking the Connection;
4. inserts one immutable ConnectionRevision with its schema version and canonical
   content hash;
5. transitions a `DRAFT` Connection to `ACTIVE` on its first publication;
6. records the publication AuditEvent;
7. commits all effects atomically.

Publishing a later revision does not change existing BindingRevision records.
Bindings continue to reference their exact ConnectionRevision until separately
republished or rolled back.

Connection does not gain a mutable `current_revision_id` or `active_revision_id`
pointer. The latest revision is authoring metadata, not a runtime selection.
Binding publication selects the exact ConnectionRevision used for execution.

A `DISABLED` Connection is a mutable global runtime kill switch. Draft editing and
revision publication may continue while disabled, but publication does not
re-enable it. Re-enabling is an explicit lifecycle operation.

`ARCHIVED` is terminal in the initial model. Archived Connections cannot receive
new drafts, revisions, access changes, Credentials, Operations, or Bindings.
Historical revisions and execution lineage remain readable. Hard deletion is not
a normal lifecycle operation.

### Workspace lifecycle

Active members with `connection:read` may list and read Connection metadata while
the Workspace is `ACTIVE`, `SUSPENDED`, `ARCHIVED`, or `PENDING_DELETION`.

Connection creation, draft authoring, publication, Project-access replacement,
and re-enabling require an `ACTIVE` Workspace. Disabling an ACTIVE Connection is
also allowed while the Workspace is `SUSPENDED` so an administrator can apply an
emergency kill switch. Archiving is initially limited to an ACTIVE Workspace.

Workspace lifecycle conflicts do not masquerade as authentication failures.

### Project-access policy

Connection is Workspace-owned and is not nested below one Project. Its access
policy has exactly one of these modes:

- `WORKSPACE`: every Project in the same Workspace may use the Connection;
- `SELECTED_PROJECTS`: only Projects named by current
  `connection_project_access` rows may use it.

An empty `SELECTED_PROJECTS` set is valid and means deny-all. This permits safe
staging before any Project receives access.

The control API requires callers to choose the access policy explicitly when
creating a Connection. It does not rely on the database's `WORKSPACE` default.
OWNER and ADMIN may create either mode. A BUILDER-created Connection must use
`SELECTED_PROJECTS` and may begin with an explicit same-Workspace Project set or
with the empty deny-all set.

For canonical state:

- `WORKSPACE` mode has no `connection_project_access` rows;
- `SELECTED_PROJECTS` mode contains exactly the selected same-Workspace rows and
  may contain zero rows;
- switching to `WORKSPACE` deletes any prior selected-Project rows;
- replacing selected access validates every Project under the same locked
  Workspace authorization boundary;
- duplicate Project IDs are rejected during request validation.

An access replacement accepts at most 1,000 selected Project IDs. Larger changes
must be split at a higher product boundary rather than creating an unbounded
authorization query or transaction.

OWNER and ADMIN may change the access mode and replace the selected-Project set.
BUILDER may replace the selected-Project set only while the Connection already
uses `SELECTED_PROJECTS`; BUILDER cannot grant Workspace-wide access or change a
Workspace-wide Connection back to selected access.

Access replacement is one transaction. The repository locks the Connection and
the addressed Project rows, verifies same-Workspace ownership, replaces the
access rows, updates `access_mode`, and records one AuditEvent. It never exposes a
partially replaced policy.

Project access is independently checked during Binding publication and every
runtime admission. Revocation does not mutate or delete historical
BindingRevision records, but it immediately makes affected Bindings non-runnable
after the access transaction commits. Cached immutable configuration cannot
override current Connection access state.

Reading Connection metadata does not itself grant a Project the right to use the
Connection.

### Existence hiding

The Workspace-scoped API preserves the existing tenant boundary:

- an absent Workspace and a missing or ended WorkspaceMembership both produce
  `WORKSPACE_NOT_FOUND`;
- within a visible Workspace, an absent Connection and a Connection belonging to
  another Workspace both produce `CONNECTION_NOT_FOUND`;
- an invalid Workspace path is resolved before Connection existence is disclosed;
- Connection queries never load by `connection_id` alone.

A selected Project identifier that is absent or belongs to another Workspace is
reported as `PROJECT_NOT_FOUND` during access replacement. No partial access
update commits.

### Transactional mutations and audit

Connection creation is one PostgreSQL transaction containing:

1. authorization against the active WorkspaceMembership and ACTIVE Workspace;
2. one `DRAFT` Connection;
3. zero or more validated selected-Project access rows;
4. one immutable TENANT-scope `CONNECTION_CREATED` AuditEvent.

Publication, access replacement, disable, re-enable, and archive are separately
atomic operations. Their successful material state changes create immutable
AuditEvents using the membership role read inside the transaction. Mutable draft
autosave does not create one AuditEvent per write; publication records the
durable configuration change without storing secret material.

Audit snapshots may contain safe Connection identity, lifecycle, access-policy,
revision number, schema version, and configuration-hash metadata. They never
contain Credential material or unredacted sensitive provider configuration.

Future membership-ending and Workspace lifecycle mutations must acquire
compatible locks so authority cannot end between authorization and a committed
Connection mutation.

### Initial HTTP surface

The Connection API is nested under the authorized Workspace:

```text
POST /v1/workspaces/{workspace_id}/connections
GET  /v1/workspaces/{workspace_id}/connections
GET  /v1/workspaces/{workspace_id}/connections/{connection_id}
PATCH /v1/workspaces/{workspace_id}/connections/{connection_id}
GET  /v1/workspaces/{workspace_id}/connections/{connection_id}/draft
PUT  /v1/workspaces/{workspace_id}/connections/{connection_id}/draft
GET  /v1/workspaces/{workspace_id}/connections/{connection_id}/revisions
POST /v1/workspaces/{workspace_id}/connections/{connection_id}/revisions
GET  /v1/workspaces/{workspace_id}/connections/{connection_id}/revisions/{revision_id}
PUT  /v1/workspaces/{workspace_id}/connections/{connection_id}/access
```

The metadata PATCH initially permits display-name changes only. Provider identity,
Workspace ownership, access, lifecycle, and revision state use their explicit
operations rather than a generic partial update.

Revision-list responses expose safe revision metadata. Reading or writing the
draft and reading full revision configuration require `connection:author`; the
general Connection list/detail surface never embeds configuration JSON.

Lifecycle endpoints are introduced with the second increment of this domain
rather than overloading general update:

```text
POST /v1/workspaces/{workspace_id}/connections/{connection_id}:disable
POST /v1/workspaces/{workspace_id}/connections/{connection_id}:enable
POST /v1/workspaces/{workspace_id}/connections/{connection_id}:archive
```

The list contract uses deterministic `created_at DESC, id DESC` ordering, a
default limit of 50, a maximum limit of 100, and a versioned opaque cursor. It
includes every lifecycle state.

The revision-list contract orders by monotonic `revision_number DESC` and uses
`before_revision` keyset pagination with the same default limit of 50 and maximum
limit of 100. Revision history queries are never unbounded.

Connection creation and publication do not receive ad hoc idempotency semantics.
Generic control-plane mutation idempotency remains a separate deliberate
contract.

### Public failure contract

The initial stable failures are:

| Situation | HTTP | Code |
| --- | ---: | --- |
| Workspace absent or membership missing/ended | 404 | `WORKSPACE_NOT_FOUND` |
| Connection absent or belongs to another Workspace | 404 | `CONNECTION_NOT_FOUND` |
| Selected Project absent or belongs to another Workspace | 404 | `PROJECT_NOT_FOUND` |
| Active role lacks the requested permission | 403 | `WORKSPACE_PERMISSION_DENIED` |
| Workspace lifecycle blocks the mutation | 409 | `WORKSPACE_NOT_ACTIVE` |
| Connection lifecycle blocks the mutation | 409 | `CONNECTION_STATE_CONFLICT` |
| Provider key or configuration is unsupported/invalid | 422 | `REQUEST_VALIDATION_FAILED` |
| Invalid name, access policy, limit, or cursor | 422 | `REQUEST_VALIDATION_FAILED` |

Authentication failure remains `AUTH_INVALID_CREDENTIALS`. Clients branch on the
stable code rather than problem title or detail.

### Schema and database-role impact

The existing Connection tables remain authoritative. The implementation adds an
index supporting the accepted list order:

```sql
CREATE INDEX idx_connections_workspace_created_id
    ON connections(workspace_id, created_at DESC, id DESC);
```

The control-plane database role must not retain blanket update authority over
Connection identity. Its update rights on `connections` are narrowed to mutable
columns such as `name`, `access_mode`, `status`, `updated_at`, and `archived_at`.
`workspace_id` and `provider_key` are not updateable by the application role.

Update rights on `connection_drafts` are narrowed to `draft_json`,
`updated_by_user_id`, and `updated_at`; its parent identity is immutable. The
control-plane role receives the narrow DELETE privilege on
`connection_project_access` required for atomic access replacement, while access
rows themselves are never updated in place.

ConnectionRevision remains insert/select-only under application roles. Database
constraints continue enforcing same-Workspace revision and Project-access
relationships; service policy owns lifecycle and access-mode semantics that span
multiple rows.

## Initial implementation boundary

The Connection domain is delivered in two reviewable increments:

1. stable identity, authorization, create/list/detail/rename, Project-access
   replacement, pagination, database ACL hardening, and audit;
2. typed provider registry, draft authoring, immutable revision publication,
   activation, and lifecycle operations.

Credential creation, secret encryption, Operation authoring, Binding publication,
runtime execution, health checks, connection testing, OAuth, and provider-native
adapters are outside this ADR's implementation slice.

## Consequences

- Connection authorization extends the established WorkspaceMembership boundary;
- Connection identity and provider meaning cannot drift across historical
  revisions;
- Builders can author integrations and assign selected Projects without receiving
  Workspace-wide access or global lifecycle authority;
- Viewers can inspect safe metadata but cannot read drafts or mutate Connections;
- Project sharing remains explicit, same-Workspace, atomic, and independently
  enforceable at publication and runtime;
- an empty selected-project policy provides a safe deny-all staging state;
- access revocation blocks runtime without rewriting immutable history;
- immutable revision publication remains separate from mutable draft autosave;
- no ambiguous mutable latest-revision pointer is introduced;
- disabling is an explicit global kill switch and archiving preserves lineage;
- application-role ACLs protect immutable Connection identity columns;
- provider configuration remains typed and secret-free;
- the initial slice adds several endpoints and transactions, but avoids coupling
  Connection delivery to Credential or runtime implementation.

## Alternatives considered

### Project-owned Connections

Rejected. It would duplicate shared external-account configuration and contradict
the accepted Workspace-owned aggregate model.

### Treat access rows as advisory publication metadata

Rejected. Revocation must remain effective against already-published immutable
Bindings, so current access state is a runtime admission dependency.

### Mutable current Connection configuration

Rejected by ADR 0002 because it would silently change historical and in-flight
runtime meaning.

### A mutable active ConnectionRevision pointer

Rejected. BindingRevision already pins the exact revision used for execution.
Adding a second runtime pointer would create ambiguous composition and cache
invalidation semantics.

### Permit provider-key changes

Rejected. Provider identity determines configuration schema and capabilities;
changing it would reinterpret historical Connection identity.

### Require at least one selected Project

Rejected. Deny-all is a useful safe staging state and avoids granting temporary
Workspace-wide access during setup.
