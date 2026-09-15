# Product Scope

## Thesis

Backend for Framer is a Framer-native hosted backend for secure server-side API access, mutations, background work, webhooks, synchronization, and operational visibility.

It is not a generic BaaS or workflow builder in V1.

## Core production boundary

Core 0–4 together define production readiness.

### Core 0 — Foundation
Accounts, Workspaces, Projects, Framer connection, Connections, Credentials, Operations, Bindings, execution, Usage, observability, security, and failure handling.

### Core 1 — Queries
Secure read operations.

### Core 2 — Actions
State-changing interactions for forms, buttons, and components.

### Core 3 — Sync
Provider-neutral synchronization engine with Framer-first adapters and UX.

### Core 4 — Triggers and Jobs
Inbound webhooks, schedules, and durable background work.

## Later/private maturity

OAuth expansion, richer provider adapters, ready-made components/forms, recipes, dynamic data helpers, and advanced agency tooling.

Feature maturity is independent from Core numbering: Experimental, Internal, Private Preview, Production Candidate, GA.

## Explicit non-goals for initial core

- arbitrary user code execution
- generic serverless functions
- generic ETL/workflow-builder UX
- exactly-once external side effects
- full auth-as-a-service
- marketing email platform
- hidden bidirectional sync
- separate execution engines per provider
- separate schedulers for Sync
