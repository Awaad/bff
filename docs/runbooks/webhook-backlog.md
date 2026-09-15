# Runbook: Webhook Processing Backlog

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger

Accepted WebhookDeliveries accumulate in ACCEPTED/PROCESSING or queue age exceeds SLO.

## Safety

Do not ask providers to resend already accepted events unless dedupe semantics are understood. Do not delete accepted Deliveries to clear the queue.

## Diagnose

1. Check ingress acceptance vs processing rate.
2. Check Outbox/RabbitMQ state.
3. Identify one Endpoint/provider dominating volume.
4. Check target Binding/Credential health.
5. Check repeated deterministic failures vs worker capacity.

## Recover

Restore consumer capacity or dependent runtime health. Reprocess through normal idempotent Delivery/Execution pathways. Persist DEAD_LETTERED when retries are exhausted.
