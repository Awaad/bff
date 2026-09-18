# ADR 0020: Workspace authorization boundary

**Status:** Accepted  
**Date:** 2026-09-18

## Context

Authentication now resolves a real WorkOS AuthKit session to an admitted internal
BFF `users.id`. The next control-plane boundary is tenant authorization.

A valid BFF login must not imply access to any Workspace. WorkOS organization,
role, or permission claims are authentication-provider data and are not the source
of truth for BFF tenant access.

The V2.1 schema already models Workspace membership as historical periods with
roles `OWNER`, `ADMIN`, `BUILDER`, and `VIEWER`. An active membership is represented
by `ended_at IS NULL`, and the database prevents more than one active membership
for the same `(workspace_id, user_id)` pair.

A newly provisioned User also needs a safe path to create the first Workspace.
Without that bootstrap operation, authenticated users can be valid principals but
cannot enter the product's tenant model.

## Decision

### Authorization source of truth

Workspace authorization is derived from the canonical internal `users.id` plus an
active `workspace_memberships` row.

```text
authenticated users.id
    -> workspace_memberships
    -> Workspace role
    -> BFF permission policy
```

No WorkOS organization, role, or permission claim grants Workspace access.

PostgreSQL remains the authorization source of truth for this boundary. V1 does
not add a positive Valkey/Redis Workspace-authorization cache.

### Active membership

A membership is active when:

```text
ended_at IS NULL
```

Historical ended memberships never authorize current access.

Role names are permission bundles, not authentication roles. The initial
implemented permission is Workspace metadata read. `OWNER`, `ADMIN`, `BUILDER`,
and `VIEWER` all receive that permission.

Future write permissions are added explicitly to Workspace policy rather than
inferred from role ordering.

### Service-layer enforcement

Workspace authorization is enforced by the Workspace domain service and its
repository contract, not only by FastAPI routers.

Repository reads are membership-constrained queries. The implementation does not
load an arbitrary Workspace first and then rely on transport code to remember to
check membership.

This keeps the authorization boundary reusable by future non-HTTP callers.

### Existence hiding

For a request addressing one Workspace, these cases are deliberately
indistinguishable to an authenticated nonmember:

- the Workspace does not exist;
- the Workspace exists but the User has no active membership.

Both produce the public `WORKSPACE_NOT_FOUND` problem.

This avoids turning Workspace UUIDs into a tenant-existence oracle.

### Workspace lifecycle

Workspace lifecycle and membership authorization are separate concerns.

An active member may read Workspace metadata when the Workspace is `ACTIVE`,
`SUSPENDED`, `ARCHIVED`, or `PENDING_DELETION`. This permits lifecycle/status UX
without treating suspension as disappearance.

Future mutation services must separately enforce the lifecycle states in which a
specific mutation is allowed.

### Workspace creation bootstrap

Any admitted authenticated BFF User may create a Workspace in this initial
control-plane surface.

Creation is one PostgreSQL transaction containing:

1. an `ACTIVE` Workspace;
2. one active `OWNER` membership for the creator;
3. one immutable TENANT-scope `WORKSPACE_CREATED` AuditEvent attributed to the
   authenticated User and local AuthSession.

If any of those writes fail, none of them commit.

Workspace creation does not use email or WorkOS provider roles to establish
ownership.

### Owner invariant

The existing invariant remains authoritative:

> An ACTIVE Workspace retains at least one active OWNER.

The creation path satisfies it immediately. Future role-change and membership-end
operations must enforce it transactionally before they are introduced.

### Initial HTTP surface

The first Workspace API is intentionally small:

```text
POST /v1/workspaces
GET  /v1/workspaces
GET  /v1/workspaces/{workspace_id}
```

Invitations, membership administration, Project CRUD, and billing are outside this
slice.

Workspace creation is not silently given an ad hoc idempotency contract. Generic
control-plane idempotency semantics will be designed deliberately rather than
reusing runtime Action idempotency by accident.

## Consequences

- authentication and authorization stay separate;
- the first non-auth domain establishes a reusable service/repository boundary;
- provider authorization claims cannot bypass BFF membership state;
- ended memberships cannot leak historical authority;
- nonmember reads do not reveal whether a Workspace exists;
- Workspace creation has durable ownership and audit state from its first commit;
- later membership mutation must preserve the last-active-OWNER invariant;
- high-cardinality list pagination remains a separate API contract decision rather
  than being improvised in this bootstrap surface.
