# ADR 0015: Durable control-plane session admission

**Status:** Accepted  
**Date:** 2026-09-17

## Context

ADR 0014 establishes `users.id` as the internal BFF principal and maps a
server-verified OIDC `(iss, sub)` identity through `user_auth_identities`.

Cryptographically valid provider access tokens are necessary but not sufficient
for BFF authorization. We need a local, durable way to stop a session immediately,
enforce a BFF-owned absolute admission lifetime, and evaluate current Workspace
authorization without waiting for an upstream access token to expire.

At the same time, BFF must not reimplement the authentication provider's credential
ceremonies, MFA/passkeys, refresh-token protocol, session inactivity policy, or
signing-key infrastructure.

## Decision

### Local admission is mandatory

Every authenticated control-plane request must satisfy both:

1. provider token verification;
2. an ACTIVE local BFF session admission.

A provider JWT that is otherwise valid is rejected if its provider session has no
matching local BFF admission.

The local admission record is `auth_sessions`.

### Session identity

The local row has an internal UUIDv7 `id` and references exactly one
`user_auth_identities` row.

The upstream provider session is identified by `provider_session_id`. For WorkOS
AuthKit this is the JWT `sid`.

The durable lookup path is therefore:

```text
validated (iss, sub)
    -> user_auth_identities.id
    -> (user_auth_identity_id, provider_session_id)
    -> auth_sessions.id
```

The provider session ID is opaque. BFF does not normalize it.

### Local lifetime

`auth_sessions.expires_at` is an immutable absolute local admission deadline.

It is set when the session is admitted and is never extended by access-token or
refresh-token rotation.

Effective session state is derived:

```text
REVOKED  if revoked_at IS NOT NULL
EXPIRED  if now() >= expires_at
ACTIVE   otherwise
```

There is no background job whose correctness is required to mark a row EXPIRED.

The effective request lifetime is always bounded by all applicable authorities:

- provider JWT `exp`;
- provider session lifecycle;
- BFF `auth_sessions.expires_at`;
- User and UserAuthIdentity kill switches.

BFF may be stricter than the provider, never more permissive.

### Revocation

Local revocation is authoritative for BFF and happens first.

A successful local revocation transaction:

1. records `revoked_at` and a machine-readable `revocation_reason`;
2. writes the security AuditEvent in the same transaction where practical;
3. emits durable reconciliation work through the transactional outbox.

The request path stops accepting the session as soon as the database transaction
commits. It does not wait for the authentication provider.

Provider revocation is reconciled asynchronously. `provider_revoked_at` records
provider confirmation or a trusted provider revocation event.

Provider-originated revocation can only reduce authority. It never creates or
reactivates a local admission.

Revocation is monotonic at the domain-service layer. Ordinary workflows do not
clear or rewrite an existing revocation.

### Kill switches

Every request also requires:

- `users.status = ACTIVE`;
- `user_auth_identities.status = ACTIVE`.

Disabling a User or UserAuthIdentity is therefore an immediate kill switch even if
individual session rows have not yet been bulk-marked revoked.

The corresponding domain operation should also revoke affected active local
sessions transactionally so stored session state converges with the kill switch.

Ending a WorkspaceMembership removes access to that Workspace without requiring a
global logout.

### Provider responsibilities

The authentication provider owns:

- sign-in ceremonies;
- password/MFA/passkey recovery;
- refresh-token semantics and rotation;
- provider inactivity timeout;
- provider maximum session lifetime;
- provider signing-key rotation.

BFF does not implement a second refresh-token protocol.

`auth_sessions` never stores access tokens or refresh tokens.

If a later server-side transport requires BFF to retain a provider refresh token,
that secret belongs in an encrypted credential/session-secret facility separate
from the admission row.

### Access-token identifiers

BFF does not persist every JWT `jti`.

`jti` may be used in request telemetry and security diagnostics after redaction
policy review, but the durable session identity is the provider `sid`.

### JWKS rotation

The provider adapter verifies JWTs locally using an explicitly configured trusted
issuer/client context and JWKS source.

The verifier:

- allowlists accepted signing algorithms;
- validates signature before trusting claims;
- validates issuer, client/audience context, `exp`, and required identity/session
  claims;
- uses `kid` only to select a candidate verification key;
- caches previously trusted JWKS for a bounded TTL;
- performs one immediate JWKS refresh when an unknown `kid` is encountered;
- fails closed if a required key cannot be obtained or verified;
- refreshes keys proactively before cache expiry where practical.

JWKS caching is not authorization caching.

### Authorization

Provider organization, role, permission, entitlement, and feature-flag claims are
not BFF Workspace authorization.

After admission establishes `(user_id, auth_session_id)`, BFF evaluates current
WorkspaceMembership and BFF permission policy.

Authorization must be enforced at the service/domain boundary, not only in the HTTP
router.

### Cache policy

PostgreSQL is the initial source of truth for session admission and Workspace
authorization.

V1 does not positively cache "session allowed" or "membership allowed" decisions in
Valkey. That deliberately preserves immediate revocation/removal semantics.

Safe caches may be introduced later only with an explicit invalidation/versioning
protocol and documented maximum staleness.

Provider JWKS is independently cacheable because it is verification material, not
BFF authorization state.

### Provider events

Trusted, signature-verified provider events are reconciliation inputs.

For WorkOS:

- `session.created` never auto-admits a BFF session;
- `session.revoked` may revoke an existing BFF admission idempotently;
- provider organization/role events never mutate BFF Workspace authorization.

Provider event delivery must be deduplicated by stable provider event identity.

## Consequences

- We can revoke BFF access immediately without waiting for JWT expiry.
- Refresh-token rotation does not extend local authority.
- WorkOS can be replaced without changing BFF User, Workspace, or authorization
  semantics.
- Every authenticated request includes one current-state database admission check
  before Workspace authorization.
- The first implementation favors correctness over a positive auth cache.
- A separate provider adapter can implement WorkOS token/JWKS/event mechanics
  without becoming the domain model.
