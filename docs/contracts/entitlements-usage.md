# Entitlements and Usage Contract

## Entitlement resolution

Entitlements are typed capability/capacity keys derived from active grants.

A grant may be Workspace-wide or Project-specific.

Effective runtime policy is resolved from applicable grants plus platform safety limits.

Runtime must never branch on marketing plan names.

## Usage

UsageEvent is an append-only ledger with a stable dedupe key.

UsageBucket is a projection/aggregate and may be rebuilt from authoritative events where feasible.

Customer execution count is normally metered per logical Execution, not per retry Attempt.

Real cost dimensions such as transferred bytes may accumulate across Attempts.

## Quota

Valkey may provide low-latency counters, but durable usage truth remains in PostgreSQL.

Hard admission decisions must reconcile with durable truth and cannot depend solely on volatile counters.
