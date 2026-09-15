# ADR-0011: Separate Billing, Entitlements, and Usage

- **Status:** Accepted
- **Date:** 2026-09-13

## Decision

Separate Billing (purchases), Entitlements (what is allowed), and Usage (what was consumed).

Billing belongs to Workspace. Entitlements may be Workspace- or Project-scoped. Usage is primarily per Project and aggregates to Workspace.

Runtime never branches on marketing plan names.

## Invariants

- no `plan`/`is_pro` on Workspace or Project
- UsageEvent is append-only
- Valkey quota counters are non-authoritative
