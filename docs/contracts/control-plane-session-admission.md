# Control-plane Session Admission Contract

## Purpose

Define the durable BFF admission check between external token verification and
Workspace authorization.

This contract applies to authenticated customer control-plane requests from the Web
Dashboard, Framer Plugin, and future first-party clients.

## Required request evidence

A provider adapter first verifies the incoming credential and produces trusted
claims containing at minimum:

```text
issuer
subject
provider_session_id
issued_at
expires_at
token_id
```

For WorkOS AuthKit these map to:

```text
issuer              <- iss
subject             <- sub
provider_session_id <- sid
issued_at            <- iat
expires_at           <- exp
token_id             <- jti
```

The provider adapter may require additional client/audience claims.

Claims are not trusted until signature and provider policy verification succeeds.

## Admission lookup

After token verification:

1. Resolve an ACTIVE `user_auth_identities` row by exact `(issuer, subject)`.
2. Require its referenced `users` row to be ACTIVE.
3. Resolve `auth_sessions` by
   `(user_auth_identity_id, provider_session_id)`.
4. Require `revoked_at IS NULL`.
5. Require database time to be before `auth_sessions.expires_at`.
6. Establish the internal principal:

```text
user_id
auth_session_id
```

7. Evaluate current Workspace authorization.

A valid provider token with no local `auth_sessions` row is denied.

## Session creation

A BFF session is admitted only by an explicit successful BFF login/callback flow.

A provider `session.created` webhook is not authority to create a local admission.

At admission time:

- `provider_session_id` is copied from trusted provider claims;
- `expires_at` is computed from explicit BFF session policy;
- if provider session expiry is known, BFF expiration must not exceed it;
- the local expiration is immutable after insertion.

A refresh using the same provider session keeps the same local row and deadline.

A new provider `sid` requires a new local admission.

## Effective state

No persisted EXPIRED state is required.

```text
if revoked_at is not null:
    REVOKED
elif now >= expires_at:
    EXPIRED
else:
    ACTIVE
```

`revocation_reason` is required exactly when `revoked_at` is present.

`provider_revoked_at` is optional and may be set only after local revocation state
exists.

## Local revocation

Local revocation must be idempotent.

If the session is already revoked, repeat requests return the existing revocation
state and must not erase or replace the original reason.

For a newly revoked session, the transaction should write:

- local revocation state;
- a sanitized AuditEvent;
- an OutboxEvent requesting provider reconciliation.

Provider API failure does not reactivate local access.

## Provider revocation events

A verified provider `session.revoked` event is authority only to reduce access.

If the matching BFF session exists:

- mark it locally revoked if needed;
- preserve an earlier local revocation reason;
- record `provider_revoked_at`;
- audit the external security transition where useful.

Unknown or duplicate provider events must not create an admitted session.

Event ingestion must be idempotent and resilient to delivery retries.

## User and identity disablement

`users.status = DISABLED` rejects all sessions for the User.

`user_auth_identities.status = DISABLED` rejects all sessions for that identity.

The disable operation should additionally bulk-revoke currently unrevoked local
sessions in the same database transaction where practical.

Neither operation waits for provider API calls before becoming effective locally.

## Workspace authorization

Admission is global user-session state. Workspace authorization is independent.

For a requested Workspace:

- an active WorkspaceMembership is required;
- the membership role is evaluated through BFF permission policy;
- suspended/archived tenant or resource lifecycle policy still applies;
- provider `org_id`, `role`, `roles`, `permissions`, `entitlements`, and
  `feature_flags` are ignored for BFF authorization.

Membership removal is effective on the next authorization check and does not need
to revoke unrelated sessions.

## Caching

Initial implementation reads PostgreSQL for positive admission and authorization
decisions on every protected control-plane request.

Do not place an "allowed" decision in Valkey until a separate design defines a
reliable invalidation/version protocol and acceptable staleness.

Negative caching may be added only if delayed reactivation is acceptable and
explicitly documented.

## Token material

Never persist or log:

- access tokens;
- refresh tokens;
- authorization codes;
- raw JWTs;
- raw login assertions.

`auth_sessions` stores identifiers and lifecycle metadata only.

If BFF later holds provider refresh tokens for a server-side client transport, they
must be encrypted and rotated atomically outside this table.

## Observability and audit

Metrics may include result categories such as:

```text
token_invalid
identity_disabled
user_disabled
session_missing
session_revoked
session_expired
membership_missing
authorization_denied
```

Do not place token values or raw claims in metrics/logs.

Security-sensitive session creation/revocation and identity/user kill-switch changes
are auditable.
