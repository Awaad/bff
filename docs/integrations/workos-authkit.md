# WorkOS AuthKit Adapter Contract

**Role:** infrastructure adapter for the provider-neutral control-plane identity and
session contracts.

This document records the WorkOS-specific mapping. It does not make WorkOS objects
authoritative BFF domain state.

## Access-token mapping

A verified WorkOS AuthKit access token supplies:

```text
iss       -> external issuer
sub       -> external subject / WorkOS user ID
sid       -> provider session ID
jti       -> access-token identifier
iat       -> access-token issue time
exp       -> access-token expiry
client_id -> application/client context
```

BFF uses `iss`, `sub`, and `sid` for durable identity/session resolution.

`jti` is not persisted as durable session state.

WorkOS claims such as:

```text
org_id
role
roles
permissions
entitlements
feature_flags
```

are not BFF Workspace authorization.

## JWT verification

Configuration must explicitly define the expected WorkOS issuer/application context
and JWKS source.

Do not hard-code the public WorkOS issuer string because custom AuthKit domains can
change the issuer.

The adapter must:

- verify an allowlisted signing algorithm;
- resolve the JWT `kid` against trusted WorkOS JWKS;
- refresh JWKS once on unknown `kid`;
- validate the exact configured issuer;
- validate the configured WorkOS client/application context;
- validate `exp` and `iat` with bounded clock skew;
- require non-empty `sub`, `sid`, and `jti`;
- reject before domain lookup on any verification failure.

## WorkOS session lifecycle

WorkOS owns:

- maximum provider session length;
- access-token duration;
- inactivity timeout;
- refresh-token rotation;
- provider-side session revocation.

BFF configures those controls in WorkOS and also applies its own immutable local
`auth_sessions.expires_at` ceiling.

The effective permission window is the intersection, never the union.

## Refresh rotation

On a successful AuthKit refresh exchange, WorkOS returns a new access token and a
new refresh token and retires the token that was presented. AuthKit provides a
short replay grace period for concurrent/retried exchanges of the just-used refresh
token.

BFF does not copy refresh-token rotation state into `auth_sessions`.

If a client transport keeps the refresh token itself, it must persist the newly
returned token and replace the old token according to WorkOS rules.

If a future BFF server-side transport stores refresh tokens, that storage must be
encrypted and updated atomically. It is a separate design from admission state.

## Session events

Subscribe to WorkOS `session.revoked` for reconciliation.

`session.created` may be consumed for telemetry/reconciliation but must never create
local BFF authority by itself.

A verified `session.revoked` event resolves the BFF identity using the configured
WorkOS issuer plus the WorkOS user/session identifiers, then idempotently reduces
local authority.

Webhook/event IDs must be deduplicated.

## Local-first logout/revocation

For a BFF-initiated logout or security revocation:

1. commit BFF local revocation first;
2. commit AuditEvent and durable provider-reconciliation work;
3. then revoke the WorkOS session;
4. record provider confirmation/event without changing the original local
   revocation reason.

A WorkOS outage therefore cannot keep a locally revoked BFF session usable.

## Failure behavior

- Unknown `kid` + failed JWKS refresh: deny.
- Invalid/expired JWT: deny before database admission lookup.
- Missing local session: deny.
- WorkOS revocation API unavailable after local revocation: remain denied locally
  and retry reconciliation.
- WorkOS webhook duplicates: idempotent.
- WorkOS organization/role drift: does not alter BFF Workspace authorization.

## Testing requirements

The adapter test suite must cover at least:

- valid JWT;
- wrong issuer;
- wrong client context;
- expired JWT;
- unsupported algorithm;
- unknown `kid` then successful bounded JWKS refresh;
- unknown `kid` during cooldown;
- unknown `kid` and refresh failure;
- rotated signing key;
- missing `sub`, `sid`, or `jti`;
- provider session revocation event;
- duplicate revocation event;
- local revocation while WorkOS API is unavailable;
- refresh flow retaining the same BFF local absolute deadline.
