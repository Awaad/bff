# ADR 0018: Structured API problem details

**Status:** Accepted  
**Date:** 2026-09-18

## Context

The control API now has multiple meaningful failure outcomes. Ad hoc JSON `detail`
strings would make human wording an accidental client contract for the Framer
Plugin, Web Dashboard, generated TypeScript client, and future SDKs.

## Decision

BFF uses RFC 9457 Problem Details for public HTTP failures with media type:

```text
application/problem+json
```

The common representation is:

```json
{
  "type": "urn:uuid:<stable-problem-type-uuid>",
  "title": "Short human-readable summary",
  "status": 409,
  "detail": "Safe human-readable occurrence detail.",
  "instance": "urn:uuid:<request-id>",
  "code": "AUTH_ACCOUNT_LINK_REQUIRED",
  "request_id": "<uuidv7>",
  "retryable": false
}
```

Optional fields are omitted when not applicable.

`type` is the protocol identifier and `code` is the ergonomic BFF identifier for
client branching. Both come from one central registry. Clients must not parse or
branch on `title` or `detail`.

Problem-type identifiers use stable `urn:uuid:` values so the API contract does not
depend on a future public hostname.

Request validation uses one top-level problem code:

```text
REQUEST_VALIDATION_FAILED
```

and may include an `errors` extension with `pointer`, `code`, and safe `detail`.
Rejected input values are never reflected.

The following internal authentication distinctions intentionally collapse to one
public problem:

```text
bad token
wrong issuer/client
missing identity
disabled identity
disabled User
missing session
revoked session
expired session
```

Public result:

```text
AUTH_INVALID_CREDENTIALS
```

Actionable client states remain distinct:

```text
AUTH_EMAIL_VERIFICATION_REQUIRED
AUTH_ACCOUNT_LINK_REQUIRED
AUTH_PROVIDER_UNAVAILABLE
```

Unhandled exceptions become `INTERNAL_ERROR`. Raw exception strings, SQL,
provider bodies, tokens, secrets and stack traces are never copied into public
Problem Details.

## Consequences

- client behavior no longer depends on English strings;
- authentication remains enumeration-resistant;
- OpenAPI must describe `application/problem+json` accurately;
- future public problems are added through one registry;
- changing an existing code/type semantic is a breaking API change.
