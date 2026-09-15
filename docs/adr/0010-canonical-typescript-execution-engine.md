# ADR-0010: Canonical TypeScript Operation Execution Engine

- **Status:** Accepted
- **Date:** 2026-09-13

## Decision

Use one TypeScript/Node execution engine for Query, Action, Job, Webhook-triggered, and Sync external API execution.

Python/FastAPI remains the control-plane language.

Provider-native Operations compile into the same canonical executable representation and do not bypass central HttpTransport/security rules.

## Rationale

The workload is network-I/O heavy and benefits from Fetch/Web APIs, streams, AbortSignal, multipart/file handling, and direct alignment with the Framer TypeScript ecosystem.

## Invariants

- no hidden second provider executor
- Sync external API work reuses the canonical executor
- synchronous and async execution share the same Operation contract
