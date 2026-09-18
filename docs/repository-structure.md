# Repository Structure Contract

This document defines the dependency and placement rules for the Backend for
Framer monorepo. It is an engineering contract, not a descriptive snapshot.

## Top-level layout

```text
apps/
  Deployable synchronous/user-facing applications.

workers/
  Independently deployable asynchronous workers.

packages/
  Reusable packages shared by deployables. Shared packages must never import a
  deployable application or worker.

scripts/
  Repository, development, migration and operations tooling. Production
  application code must not import repository scripts.

tests/
  Cross-package unit, integration, schema, ACL and end-to-end tests.

infra/
  Local/deployment infrastructure configuration.

docs/
  Architecture, ADRs, engineering contracts and runbooks.
```

## Python control plane

```text
apps/control-api/src/bff_control/
├── api/
│   HTTP transport and request/response adaptation only.
├── core/
│   Process-wide primitives: settings, errors, logging, IDs and clocks.
├── infrastructure/
│   Database, messaging, KMS and provider/client infrastructure.
└── domains/
    Domain modules. Each domain owns its service, repository interfaces,
    persistence models, schemas, enums and policies.
```

### API transport layout

The control API is organized by transport responsibility before route family:

```text
api/
├── app.py
├── contracts.py
├── context.py
├── dependencies/
├── middleware/
├── problems/
└── routes/
    ├── health.py
    └── v1/
```

Placement rules inside `api`:

- `routes/` owns `APIRouter` endpoint collections;
- versioned public routes live under `routes/v1/`;
- `dependencies/` owns reusable FastAPI dependency adapters;
- `middleware/` owns thin cross-cutting ASGI transport behavior;
- `problems/` owns the public HTTP Problem Details protocol and exception mapping;
- `context.py` owns request correlation state shared by API transport helpers;
- `app.py` composes middleware, exception handlers and routers;
- do not place new endpoint modules flat at the `api/` root.

A route module should normally group one resource or bounded transport surface. If
one route family becomes materially complex, it may graduate from one module to a
subpackage without changing the surrounding transport layout.

### Placement rules

- `core` must not import `domains`, `api`, or `infrastructure`.
- `domains` must not import `api`.
- one domain must not import another domain's repository implementation or
  persistence models;
- infrastructure may depend on `core` and may implement interfaces required by
  domains;
- API code may invoke domain services but must not become the home of business
  rules;
- database engines/session factories belong under `infrastructure/db`, not
  `core`;
- environment/runtime configuration belongs in `core/settings.py`;
- avoid parallel `config.py` and `settings.py` modules unless they represent
  genuinely different concepts.

## TypeScript deployables

- `apps/*` may depend on `packages/*`;
- `workers/*` may depend on `packages/*`;
- `packages/*` must not depend on `apps/*` or `workers/*`;
- `workers/*` must not import `apps/*`.

The repository boundary checks under `tests/boundaries/` enforce the currently
machine-checkable subset of these rules.

## Database ownership

- Alembic migration files and their migration-owned SQL assets are deployable
  database history.
- accepted schema/ACL documents are reviewed specifications.
- after a migration is committed/applied, correct it with a new migration;
  never edit deployed history.
- schema and ACL regression tests use a disposable PostgreSQL database and the
  same migration/role assets used by deployment.

## Tests

```text
tests/
├── unit/
├── integration/
├── schema/
├── acl/
├── boundaries/
├── e2e/
└── support/
```

Schema tests exercise PostgreSQL constraints directly. ACL tests connect as
real temporary LOGIN principals that inherit the production NOLOGIN
application roles. Tests must not be changed merely to accommodate an
implementation defect.
