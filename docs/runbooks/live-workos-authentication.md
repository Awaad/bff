# Live WorkOS authentication proof

## Purpose

Exercise the real WorkOS AuthKit PKCE flow against the local BFF control API
without introducing a temporary frontend or storing provider tokens.

This is development verification tooling, not an application login surface.

## WorkOS dashboard

Use the WorkOS staging application whose API key begins with `sk_test_`.

Configure this exact Redirect URI:

```text
http://127.0.0.1:8787/callback
```

CORS does not need to be configured for this proof. The browser only visits
WorkOS AuthKit. The code exchange and WorkOS User lookup are made by local Python
processes, not browser JavaScript.

## Local environment

`WORKOS_CLIENT_ID` is not read by the BFF control API. Use:

```dotenv
BFF_WORKOS_API_KEY=sk_test_<real value>
BFF_AUTH_CLIENT_ID=client_<real value>

BFF_AUTH_ISSUER=https://api.workos.com
BFF_AUTH_JWKS_URL=https://api.workos.com/sso/jwks/client_<real value>
```

Keep the existing local database values.

If the WorkOS application uses a custom authentication domain, do not use the
default issuer/JWKS values above. Configure its exact issuer/JWKS contract.

Never commit `.env`.

## Start dependencies

```bash
docker compose --env-file .env up -d postgres
```

Ensure migrations and roles are current using the repository's normal local
database procedure.

## Start the control API

In one terminal:

```bash
uv run uvicorn bff_control.main:app   --host 127.0.0.1   --port 8000
```

Check:

```bash
curl -fsS http://127.0.0.1:8000/livez
curl -fsS http://127.0.0.1:8000/readyz
```

Both must succeed before running the live probe.

## Run the probe

In a second terminal:

```bash
uv run python scripts/auth/workos_live_probe.py
```

The script:

1. checks BFF liveness/readiness;
2. generates an in-memory PKCE verifier/challenge and CSRF state;
3. opens AuthKit in the default browser;
4. receives the authorization callback on loopback only;
5. exchanges the code using `code_verifier` and no client secret;
6. checks token `iss` and `client_id` against BFF settings;
7. proves `BFF_WORKOS_API_KEY` can fetch the verified WorkOS User;
8. calls `POST /v1/auth/session`;
9. repeats the same call and proves local expiry is unchanged;
10. calls authenticated `GET /v1/me`.

Access tokens, refresh tokens, authorization codes, API keys, and PKCE verifiers
are never printed or written to disk.

If automatic browser opening is unavailable:

```bash
uv run python scripts/auth/workos_live_probe.py   --print-authorization-url
```

Treat that one-time URL as ephemeral authentication material.

## First-time provisioning proof

For the strongest first run, authenticate a WorkOS User that has never been mapped
into the local BFF database.

That proves:

```text
verified WorkOS access token
    -> WorkOS User Management lookup
    -> BFF User
    -> user_auth_identity
    -> auth_session
    -> audit event
```

Within one probe, repeated `POST /v1/auth/session` calls use the same WorkOS `sid`
and must not extend the immutable BFF local TTL.

## Database inspection

After the first successful run, confirm:

- one BFF User for the normalized email;
- one `user_auth_identities` row for exact `(issuer, subject)`;
- one `auth_sessions` row for that WorkOS `sid`;
- one `AUTH_SESSION_CREATED` audit event for the new local session.

Do not edit rows to make the proof pass.

## Failure interpretation

`AUTH_INVALID_CREDENTIALS`
: Verify exact issuer, client ID, JWKS URL, token timing, and local session state.

`AUTH_EMAIL_VERIFICATION_REQUIRED`
: Complete WorkOS email verification. Do not bypass the BFF requirement.

`AUTH_ACCOUNT_LINK_REQUIRED`
: The verified email collides with another BFF User. Use the future explicit
account-linking flow, never automatic linking.

`AUTH_PROVIDER_UNAVAILABLE`
: Check the WorkOS API key and WorkOS User Management availability.

The probe does not print raw WorkOS response bodies or provider tokens.
