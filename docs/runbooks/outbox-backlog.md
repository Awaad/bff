# Runbook: Outbox / RabbitMQ Backlog

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger

Oldest unpublished OutboxEvent exceeds SLO, RabbitMQ queue age/depth rises, or async product work is delayed.

## Safety

Do not bulk-republish by bypassing domain idempotency. Do not mark events published without broker-confirm semantics.

## Diagnose

1. Check PostgreSQL and outbox claim rate.
2. Check dispatcher replicas/errors.
3. Check RabbitMQ connectivity/queue state.
4. Compare oldest outbox age and broker queue age.
5. Identify dominant event type/tenant.
6. Check downstream consumer capacity.

## Mitigate

Restore dispatcher connectivity/capacity, scale the relevant consumers, quarantine pathological traffic through supported controls, and allow stale leases to be reclaimed.

## Verify

Outbox age and queue age fall, duplicate delivery remains harmless, and no product state was manually rewritten.
