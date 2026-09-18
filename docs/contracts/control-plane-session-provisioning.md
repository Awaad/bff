# Control-plane Session Provisioning Contract

## Entry point

Public clients establish local BFF admission with:

```text
POST /v1/auth/session
Authorization: Bearer <provider access token>
```

The request has no identity/profile body.

## Trusted inputs

The access token must first pass the provider-neutral verifier. Provisioning uses
only the trusted `issuer`, `subject`, and `provider_session_id` claims.

For a known exact identity, provider profile lookup is skipped.

For a new identity, the server fetches the provider User by verified subject and
requires an exact subject match plus a verified non-empty email.

## First User creation

`email_normalized` is `email.strip().casefold()` only.

An email collision never links identities automatically. If the exact external
identity still does not exist after resolving database races, the operation returns
account-link-required.

## Local admission

The first insertion uses database time and the configured absolute TTL. The default
is 604800 seconds.

Repeated provisioning of the same active `(identity, provider_session_id)` returns
the existing admission and preserves the original expiry.

An expired or revoked admission is never reactivated for the same provider session
ID.

## Audit

A newly inserted AuthSession writes `AUTH_SESSION_CREATED` as a PLATFORM AuditEvent
in the same transaction. Reusing an existing admission does not create another
audit event.

## Failure classes

Public API mapping:

```text
invalid/unknown/disabled provider identity -> 401
provider User missing                       -> 401
unverified first-login email                -> 403
existing BFF email collision                -> 409
provider profile API unavailable            -> 503
```

Database/infrastructure failures are not converted into credential failures.
