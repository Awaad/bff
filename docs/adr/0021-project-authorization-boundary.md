# ADR 0021: Project authorization boundary

**Status:** Accepted  
**Date:** 2026-09-21

## Context

The Workspace control-plane slice establishes authenticated internal Users,
durable AuthSessions, active WorkspaceMembership authorization, existence hiding,
and transactional Workspace creation.

Project is the next Phase 1 domain. A Project belongs to exactly one Workspace and
is the tenant-local root for later Bindings, runtime admission, execution history,
Jobs, Webhooks, and Sync. The initial Project API must therefore preserve the
Workspace authorization boundary without inventing a second identity system or
leaking cross-tenant Project existence.

The V2.1 schema already provides `projects` with:

- immutable Workspace ownership during normal operation;
- lifecycle states `ACTIVE`, `SUSPENDED`, `ARCHIVED`, and `PENDING_DELETION`;
- tenant-aware uniqueness through `(workspace_id, id)`;
- no requirement for a FramerProjectLink at creation time.

The schema does not provide Project-specific memberships. Whether Project-level
ACL restrictions are needed remains a deliberately deferred product decision.

## Decision

### Authorization source of truth

The initial Project surface is authorized through the canonical internal User and
an active WorkspaceMembership:

```text
authenticated users.id
    -> active workspace_memberships row
    -> Workspace role
    -> Project permission policy
```

No WorkOS organization, role, permission, or entitlement claim grants Project
access.

V1 does not add Project-specific membership or ACL tables. If product evidence
later requires Project-level restrictions, they are introduced as an explicit
authorization model and migration rather than inferred from Framer identity or
embedded in ad hoc resource filters.

### Initial permissions

Roles remain permission bundles. The first Project permissions are:

| Permission | OWNER | ADMIN | BUILDER | VIEWER |
| --- | :---: | :---: | :---: | :---: |
| `project:read` | yes | yes | yes | yes |
| `project:create` | yes | yes | yes | no |

`project:read` covers list and detail metadata reads for every Project lifecycle
state. `project:create` permits the Framer Plugin and Dashboard builder workflow
without granting VIEWER a mutation capability.

An active VIEWER attempting Project creation receives an explicit permission
denial. The API does not hide a Workspace that the User is already authorized to
read. Permission is evaluated before Workspace lifecycle so a role without
`project:create` receives the same denial across lifecycle states.

Future Project mutation permissions are added explicitly. Role ordering must not
be used as an authorization shortcut.

### Service and repository enforcement

Project policy is enforced by the Project domain service, not only by FastAPI
routers.

Repository reads are constrained by all relevant identities:

- `user_id`;
- `workspace_id`;
- active WorkspaceMembership;
- `project_id` for detail reads.

The domain service owns the permission and lifecycle decisions. The repository
owns transaction and row-lock mechanics. For Project creation, the repository:

1. opens one PostgreSQL transaction;
2. loads and locks the Workspace and active WorkspaceMembership;
3. supplies that transaction-scoped authorization context to the service-owned
   policy callback;
4. inserts the Project and AuditEvent only after policy succeeds;
5. commits the complete operation atomically.

A prior read followed by an unconstrained insert is not an authorization boundary.
Policy rules must not be independently reimplemented in SQL. Future membership-end
and Workspace lifecycle mutations must acquire compatible row locks so authority
cannot change between authorization and Project insertion.

This keeps the policy reusable by later non-HTTP callers and prevents a membership
or lifecycle race from creating a Project after authority has ended.

### Existence hiding

The nested API distinguishes authorization layers without leaking tenant data:

- absent Workspace and missing or ended WorkspaceMembership both produce the
  public `WORKSPACE_NOT_FOUND` problem;
- within a visible Workspace, an absent Project and a Project belonging to another
  Workspace both produce the public `PROJECT_NOT_FOUND` problem;
- Project queries never load by `project_id` alone.

An invalid Workspace path is resolved before Project existence is disclosed.

### Lifecycle behavior

Active members with `project:read` may list and read Project metadata when the
Workspace is `ACTIVE`, `SUSPENDED`, `ARCHIVED`, or `PENDING_DELETION`. They may
also read Projects in every Project lifecycle state. This preserves lifecycle and
recovery UX without treating suspension or archive as disappearance.

Project creation is allowed only while the Workspace is `ACTIVE`. Creation under
`SUSPENDED`, `ARCHIVED`, or `PENDING_DELETION` is rejected as a Workspace
lifecycle conflict, not an authentication failure.

New Projects begin in `ACTIVE`. Creation does not create or activate a
FramerProjectLink. Linking remains a separate verified workflow.

Project names are trimmed, must be non-empty, and are limited to 120 characters.
Names are not unique within a Workspace because the schema and product model use
Project identity, not display name, as the stable key.

### Transactional creation and audit

Project creation is one PostgreSQL transaction containing:

1. authorization against the active WorkspaceMembership and ACTIVE Workspace;
2. one `ACTIVE` Project in that Workspace;
3. one immutable TENANT-scope `PROJECT_CREATED` AuditEvent.

The AuditEvent records `workspace_id`, `project_id`, the authenticated User, the
local AuthSession, the Workspace role snapshot read from the locked membership,
request and trace correlation, the Project display-name snapshot, and the
resulting Project state. Role data is never accepted from the caller or copied
from an earlier authorization lookup.

If authorization changes or either insert fails, the Project and AuditEvent do not
partially commit.

### Initial HTTP surface

The first Project API is nested under the authorized Workspace:

```text
POST /v1/workspaces/{workspace_id}/projects
GET  /v1/workspaces/{workspace_id}/projects
GET  /v1/workspaces/{workspace_id}/projects/{project_id}
```

The list response is deterministic and bounded. The first contract uses:

- `created_at DESC, id DESC` ordering;
- a default limit of 50 and maximum limit of 100;
- a versioned opaque cursor carrying the last returned `(created_at, id)` pair;
- `REQUEST_VALIDATION_FAILED` for a malformed cursor or invalid limit.

The cursor is only a pagination position. Every query remains independently
constrained by `user_id` and `workspace_id`, so a cursor cannot grant access. The
list includes Projects from every lifecycle state rather than silently filtering
archived records.

### Public failure contract

The initial stable failures are:

| Situation | HTTP | Code |
| --- | ---: | --- |
| Workspace absent or membership missing/ended | 404 | `WORKSPACE_NOT_FOUND` |
| Project absent or belongs to another Workspace | 404 | `PROJECT_NOT_FOUND` |
| Active role lacks `project:create` | 403 | `WORKSPACE_PERMISSION_DENIED` |
| Workspace is not `ACTIVE` for creation | 409 | `WORKSPACE_NOT_ACTIVE` |
| Invalid name, limit, or cursor | 422 | `REQUEST_VALIDATION_FAILED` |

Authentication failure remains `AUTH_INVALID_CREDENTIALS`. These codes are part
of the generated public API contract; clients do not branch on titles or details.

Project update, suspension, archive, deletion workflow, transfer, Framer linking,
and Project-level ACLs are outside this slice.

Project creation does not receive an ad hoc idempotency mechanism. Generic
control-plane mutation idempotency remains a separate deliberate contract.

### Schema impact

No Project domain table or membership migration is required. The existing
`(workspace_id, status)` index does not support the accepted pagination order, so
the slice adds an explicit migration for:

```sql
CREATE INDEX idx_projects_workspace_created_id
    ON projects(workspace_id, created_at DESC, id DESC);
```

The migration is additive, does not rewrite Project rows, and receives schema and
query-plan regression coverage. Production deployment must use the migration
policy's lock/latency review and move to `CREATE INDEX CONCURRENTLY` before the
table reaches a size where a transactional index build would threaten
availability.

## Consequences

- Project access inherits the proven Workspace tenant boundary;
- WorkOS and Framer claims cannot bypass BFF authorization state;
- the initial model does not prematurely create Project-specific ACL complexity;
- VIEWER remains read-only while BUILDER can establish a Project authoring scope;
- cross-Workspace Project identifiers do not become an existence oracle;
- creation produces durable tenant ownership and audit history atomically;
- locked authorization context prevents creation after membership authority ends;
- Project and Workspace lifecycle states remain visible while blocking invalid
  creation;
- pagination has a stable order and supporting database index;
- Framer ownership verification remains separate from internal Project creation;
- future Project-specific sharing requires an explicit model and migration.
