# ADR 0014: Provider-neutral control-plane identity

**Status:** Accepted  
**Date:** 2026-09-16

## Context

Backend for Framer has an internal `User` aggregate and Workspace memberships, but
the V2.1 baseline does not define how an authenticated external identity resolves
to `users.id`.

The Web Dashboard and Framer Plugin both need to act as the same BFF user. Framer's
Plugin API can expose client-side user/project context, but that context is not by
itself a server-verifiable BFF login assertion. Authentication therefore needs an
explicit backend identity boundary.

Email cannot safely be that boundary. Email is mutable profile/contact data, may
be recycled, and may be shared across identity providers. Automatic account
merging by email creates account-takeover risk.

## Decision

### Internal principal

`users.id` is the canonical BFF user principal.

Authorization, membership, audit attribution, and ownership decisions resolve to
this internal identifier before domain authorization is evaluated.

### External authentication identity

Server-verifiable external authentication identities are mapped through
`user_auth_identities`.

The initial external authentication protocol is OIDC. Identity is the exact pair:

```text
(issuer, subject) == (iss, sub)
```

The pair is globally unique and maps to exactly one BFF User.

OIDC issuer and subject values are opaque identity data. They are stored exactly as
validated from the trusted issuer and are not normalized like email addresses.

### Provider neutrality

No auth-vendor identifier is stored in business-domain tables.

The configured OIDC provider is an infrastructure concern. Replacing an OIDC
provider must not require changing Workspace, Project, or Membership semantics.

### Email

Email is never used to resolve an existing authenticated identity.

For first-login provisioning, application policy may require a verified email claim
to create the `users` row. If that normalized email already belongs to another BFF
User, the system must not merge automatically. Identity linking/account merging is
an explicit authenticated workflow.

### Identity lifecycle

An authentication identity may be `ACTIVE` or `DISABLED`.

Ordinary application roles may change lifecycle state, but may not mutate the
identity's `user_id`, `issuer`, or `subject`. Reassigning an external identity to a
different User is not an ordinary update.

Successful authentication requires both:

- an ACTIVE `user_auth_identities` row;
- an ACTIVE `users` row.

### Authentication vs authorization

Authentication establishes `user_id`.

Workspace authorization is evaluated separately through active
`workspace_memberships` and permission policy. Role names are permission bundles;
authentication does not imply access to any Workspace.

### Framer Plugin context

Framer Plugin user/project information is useful client context but is not accepted
as a server-verifiable BFF authentication assertion.

Framer project linking and ownership verification remain a separate security
boundary from BFF user authentication.

A browser-assisted or polling login flow may be used by the Plugin where desktop
browser handoff requires it, but that transport must ultimately resolve to the same
internal BFF `users.id`.

## Consequences

- The schema needs a durable OIDC subject mapping.
- Email-based automatic account merging is prohibited.
- Workspace endpoints can depend on one internal principal shape independent of
  auth vendor.
- Framer identity context cannot silently become an authentication bypass.
- Framer project ownership verification remains independent from user login.
- Request-token/session transport and OIDC verification are implemented in a later durable identity contract.
