# WorkOS AuthKit Session Provisioning

## Public clients

The Framer Plugin and browser dashboard use WorkOS AuthKit Authorization Code + PKCE.
Public clients do not embed the WorkOS API key.

After authentication they call BFF `POST /v1/auth/session` using the access token as
a bearer credential.

The client keeps provider refresh-token responsibility in this phase. BFF does not
persist refresh tokens.

## First-time profile lookup

Known exact BFF identities do not require a WorkOS User Management call.

For a new identity BFF requests:

```text
GET /user_management/users/{verified_sub}
Authorization: Bearer <WorkOS API key>
```

The adapter validates:

- response `id` equals the verified JWT subject exactly;
- `email` is a non-empty string;
- `email_verified` is a boolean;
- optional `name` is a string when present.

The domain requires `email_verified = true` before first-time BFF User creation.

## Provider failure behavior

A missing provider User is treated as failed authentication. Timeouts, rate limits,
invalid provider responses, and server failures are treated as temporary provider
unavailability and do not create partial local identity/session state.
