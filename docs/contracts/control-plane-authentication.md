# Control-plane Authentication Contract

## Purpose

Define how authenticated external identities become internal BFF principals before
Workspace or Project authorization is evaluated.

This contract covers customer control-plane authentication. It does not define
runtime/public Binding authentication or external provider Credentials.

## Canonical principal

The canonical authenticated principal is:

```text
user_id: UUID
```

`user_id` references `app.users.id`.

Domain services do not authorize against raw OIDC claims, email addresses, Framer
user IDs, or auth-provider-specific identifiers.

## External identity key

Initial external authentication uses OIDC.

A server-verified OIDC identity is keyed by the exact pair:

```text
issuer  = validated `iss`
subject = validated `sub`
```

`(issuer, subject)` is globally unique.

The pair is opaque and case-sensitive. Application code must not lowercase, trim,
rewrite, or otherwise normalize values after issuer validation.

## Resolution flow

For an authenticated request or session:

1. Cryptographically verify the external assertion using trusted issuer
   configuration.
2. Validate protocol requirements such as issuer, audience, expiry, signature, and
   flow-specific replay protections.
3. Extract exact `iss` and `sub`.
4. Resolve one ACTIVE `user_auth_identities` row by `(issuer, subject)`.
5. Require the referenced `users` row to be ACTIVE.
6. Resolve the provider session through an unrevoked, unexpired local
   `auth_sessions` admission.
7. Establish the internal `(user_id, auth_session_id)` principal.
8. Only then evaluate Workspace membership and permission policy.

No Workspace identifier supplied by the client is trusted as authorization context
without membership and policy evaluation.

## First-login provisioning

Provisioning is separate from ordinary identity resolution.

If policy permits automatic first-login provisioning:

- the assertion must already be server-verified;
- a verified email may be required to populate the required User profile;
- email is profile/contact data, not the external identity key;
- if `email_normalized` already belongs to another User, do not auto-link or merge;
- return an account-link-required outcome and require an explicit authenticated
  identity-link workflow.

## Identity linking and account merging

Linking another external identity to an existing User requires a separately
authenticated workflow with explicit user intent.

Ordinary application roles cannot reassign `user_auth_identities.user_id`, `issuer`,
or `subject` in place.

Account merge and recovery are privileged workflows and must be auditable.

## Lifecycle

`user_auth_identities.status`:

- `ACTIVE`: may resolve to the User.
- `DISABLED`: must not authenticate.

A disabled User cannot authenticate even through an ACTIVE external identity.

Identity rows are retained for security history; ordinary control-plane roles do
not DELETE them.

## Authorization

Authentication and authorization are separate.

After resolving `user_id`, Workspace access is determined from active
`workspace_memberships` and permission policy.

A valid identity with no active membership has no tenant access.

## Framer Plugin

Framer client APIs may provide current user/project context. Treat that context as
an input to UX and linking workflows, not as cryptographic proof of BFF identity.

Framer project ownership/access verification is independent from BFF login and
continues to follow the FramerProjectLink verification contract.

Plugin login transport may use a browser-assisted/backend-polling flow where needed,
but every successful flow must resolve through the same `(issuer, subject)` mapping
to the same BFF `user_id`.

## Security invariants

- Never resolve an existing User by email alone.
- Never auto-merge accounts because normalized emails match.
- Never trust client-supplied `user_id`, Workspace membership, or Framer user data
  as authentication proof.
- Never log bearer tokens, authorization codes, refresh tokens, or raw identity
  assertions.
- OIDC provider choice remains infrastructure configuration, not tenant/domain
  schema.
- A cryptographically valid provider token without an ACTIVE local BFF session
  admission is rejected.
- Provider organization/role/permission claims do not authorize BFF Workspaces.
- Access/refresh tokens and authorization codes are never stored in
  `auth_sessions`.
