# Local development

The root `Makefile` is the stable developer interface. It orchestrates the
repository's canonical tools; it does not replace `uv`, pnpm, Alembic, or Docker
Compose and contains no application or migration logic.


## Prerequisites

Install `uv`, Node, pnpm, Docker with Compose, and `make` before using the root
Makefile. Repository version pins remain authoritative; `make doctor` validates the
active versions before infrastructure work begins.

## First bootstrap

```bash
cp .env.example .env
```

Edit `.env` for the local machine, then run:

```bash
make bootstrap
```

`make bootstrap` is non-destructive and idempotent. It performs:

```text
make doctor
uv sync --locked
pnpm install --frozen-lockfile
docker compose --env-file .env up -d --wait
alembic upgrade head
scripts/db/bootstrap_roles.py
```

It never drops a database or deletes a Docker volume.

## Environment doctor

Run:

```bash
make doctor
```

The base doctor rejects malformed or duplicate `.env` keys, validates required
local database/Compose values, checks the pinned Python/Node/pnpm toolchain, and
runs `docker compose config --quiet`.

AuthKit values may remain placeholders during ordinary local work. They are
reported as warnings so backend work that does not need live WorkOS can proceed.

Before a real WorkOS login proof, run:

```bash
make doctor-auth
```

The auth profile requires non-placeholder WorkOS values and checks that the exact
configured client ID is represented by both the issuer and JWKS URL. The doctor
never prints secret values.

Duplicate `.env` keys are always errors. Do not rely on dotenv "last value wins"
behavior because it can hide stale security configuration.

## Infrastructure

```bash
make infra-up
make infra-status
make infra-down
```

`infra-down` intentionally does not pass `-v`; local durable volumes are kept.
Database/volume deletion remains an explicit manual operation.

## Database

```bash
make db-current
make db-sync
```

`db-sync` performs the real Alembic upgrade and then reapplies the current
application-role policy. Never use `alembic stamp head` to repair a database that
has not actually run its migrations.

## Control API

```bash
make api
```

Defaults:

```text
host: 127.0.0.1
port: 8000
```

Override when needed:

```bash
make api BFF_PORT=8080
```

## Live WorkOS proof

Configure the WorkOS staging redirect URI documented in
`docs/runbooks/live-workos-authentication.md`, then run:

```bash
make auth-live
```

This target runs `make doctor-auth` before starting the live PKCE probe.

## Quality gates

```bash
make test
make check
```

`make check` mirrors the non-PostgreSQL CI quality surface, including Python
format/lint/type tests, architecture boundaries, deterministic OpenAPI, GitHub
Action pins, Prettier, TypeScript boundaries, and API-contract checks.

PostgreSQL-marked tests require `BFF_TEST_ADMIN_URL` and run separately:

```bash
make test-db
```
