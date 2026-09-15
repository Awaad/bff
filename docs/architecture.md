# Architecture

## Intent

Backend for Framer gives Framer projects secure server-side capabilities that cannot safely live in browser code: secret-bearing API calls, mutations, files/streaming, jobs, webhooks, synchronization, notification delivery, and operational history.

The product is Framer-first. Core execution and synchronization internals are provider-neutral only where that naturally prevents duplicated reliability logic.

## Topology

```text
Framer Plugin ───────┐
Web Dashboard ───────┼──> Control Plane API (FastAPI/Python)
Internal Ops ────────┘              │
                                    │ PostgreSQL
Public Runtime ─────────────> Execution Plane (Node/TypeScript)
                                    │
                          canonical Operation Executor
                                    │
                       external APIs / native adapters

Scheduler / Outbox Dispatcher ──> RabbitMQ ──> Workers
                                      ├─ Jobs
                                      ├─ Webhooks
                                      ├─ Notifications
                                      └─ Sync

Valkey/Redis: cache, rate limiting, coordination, acceleration only.
```

Control-plane failure must not take synchronous runtime down. Queue backlog must not starve synchronous runtime.

## Durable truth

PostgreSQL is authoritative for tenant state, revisions, executions, idempotency, jobs, webhooks, sync, notifications, outbox, audit, and usage.

RabbitMQ is transport, not product truth. Redelivery is expected.

Valkey/Redis is never the sole durable record of an execution, quota, idempotency outcome, job occurrence, notification, webhook acceptance, or sync mapping.

## Domain boundaries

Expected backend shape:

```text
domains/<domain>/
├── service.py
├── repository.py
├── models.py
├── schemas.py
├── enums.py
└── policies.py
```

Routers/adapters stay outside domain packages. Core infrastructure cannot import business domains. Domains access other domains through service interfaces/contracts, not repositories/models.

## Control plane

Owns Workspaces, Projects, Connections, Credentials, Operations, Bindings, publication, Jobs, Webhooks, Sync definitions, Billing/Entitlements/Usage, AuditEvents, and customer operations/history APIs.

The control plane should not routinely decrypt customer credentials.

## Execution plane

One canonical TypeScript executor handles synchronous Query/Action and async Job/Webhook/Sync external API work.

Supported request modes: NONE, JSON, FORM_URLENCODED, MULTIPART, RAW.

Supported response modes: JSON, TEXT, BINARY, STREAM.

The executor owns bounded streaming, cancellation, safe headers, retry classification, normalized errors, credential injection, and the central SSRF/network policy.

## Immutable publication

A BindingRevision pins exact OperationVersion, ConnectionRevision, Credential, CredentialRevision, and exposure policy.

CredentialSecretVersion is resolved later so routine secret rotation does not require republish.

Publication validates and compiles the graph into an immutable executable artifact. Historical executions always record exact revision IDs.

## Reliability

- transactional outbox
- RabbitMQ durable/quorum-style delivery
- idempotent consumers
- leases and fencing
- domain-specific unique occurrence keys
- bounded retry/backoff
- durable product dead-letter state
- `INDETERMINATE` for ambiguous remote mutation outcomes

No exactly-once external-side-effect claim.

## Observability

Customer product history, platform logs/traces/metrics, and AuditEvent are separate.

## First implementation slice

```text
Workspace
→ Project
→ Connection
→ Credential
→ Operation
→ Binding publication
→ public runtime invocation
→ Execution/Attempt
→ customer history
→ AuditEvent
```

Prove this end-to-end before broadening the implementation surface.
