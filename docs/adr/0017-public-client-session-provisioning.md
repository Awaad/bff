# ADR 0017: Public-client login and local session provisioning

**Status:** Accepted  
**Date:** 2026-09-17

## Context

The Framer Plugin and browser dashboard are public clients. They cannot safely embed
server-side WorkOS credentials.

BFF also requires durable local identity and session state before a provider access
token is accepted by protected control-plane endpoints.

The verified access-token JWT gives BFF trusted external identity and session
identifiers, but first-time BFF User creation also needs trusted profile data,
including a verified email address.

## Decision

### Public clients authenticate with AuthKit PKCE

The Framer Plugin and browser dashboard use the AuthKit Authorization Code flow with
PKCE as public clients.

The client owns its provider refresh token for this phase. BFF does not persist
provider refresh tokens.

After obtaining a provider access token, the client calls:

```text
POST /v1/auth/session
Authorization: Bearer <access token>
```

This endpoint provisions or reuses BFF local admission state.

### BFF verifies before provisioning

BFF cryptographically verifies the access token before any provisioning decision.
Only trusted values from `VerifiedAccessToken` may drive local identity/session
creation.

The client cannot supply User IDs, external subjects, email addresses, or provider
session IDs in the provisioning body.

### Existing identities do not require profile lookup

If exact `(issuer, subject)` already maps to an ACTIVE UserAuthIdentity whose User
is ACTIVE, BFF may provision or reuse the local AuthSession without calling the
WorkOS User Management API.

### First-time identity requires trusted provider profile

If `(issuer, subject)` does not exist, BFF fetches the WorkOS User server-side using
the already verified `subject`.

BFF requires:

- returned WorkOS User ID exactly equals verified `subject`;
- a non-empty email;
- `email_verified = true`.

Client-supplied profile fields are never accepted as provisioning authority.

### Email is profile data, not identity

First-time User creation stores:

```text
email            = trimmed provider email
email_normalized = email.strip().casefold()
```

No dot removal, plus-address rewriting, provider-specific aliases, or mailbox
canonicalization is performed.

If `email_normalized` already belongs to another BFF User and exact
`(issuer, subject)` still does not exist after concurrency resolution, provisioning
returns account-link-required. It never auto-links by email.

### Concurrency and idempotency

Database uniqueness remains authoritative:

```text
users.email_normalized
user_auth_identities(issuer, subject)
auth_sessions(user_auth_identity_id, provider_session_id)
```

Provisioning must:

- re-resolve identity after uniqueness races;
- avoid orphan Users when an identity race is lost;
- treat repeated provisioning of the same active provider session as idempotent;
- never extend an existing AuthSession absolute expiry;
- never resurrect an expired or revoked AuthSession for the same provider session
  ID.

A new provider `sid` is required after local expiry or revocation.

### Local absolute TTL

The initial BFF local admission TTL is configurable and defaults to:

```text
7 days / 604800 seconds
```

The deadline is computed from database time when the AuthSession is first inserted.
Refreshing provider access tokens never extends the local deadline.

### Audit

Creating a new local AuthSession writes a PLATFORM AuditEvent in the same database
transaction.

Idempotent reuse of an existing admission does not write a second session-created
AuditEvent.

The initial surface is `PUBLIC_API`. Plugin/dashboard-specific attribution requires
trusted client context and is not inferred from arbitrary headers.

## Consequences

- Plugin and dashboard share one public-client login architecture.
- BFF never trusts profile data posted by the client.
- WorkOS remains authentication infrastructure, not BFF domain authority.
- Existing identities avoid the WorkOS profile API on repeated provisioning.
- First-login provider outages fail closed without partial identity state.
- Email collisions require explicit linking/recovery rather than automatic merge.
