# Webhook Ingress Contract

## Route

```text
POST /hooks/v1/{webhook_public_id}
```

`webhook_public_id` is a routing identifier, not authentication.

## Boundary

WebhookEndpoint is stable ingress identity. WebhookEndpointRevision is immutable verification/mapping configuration. WebhookDelivery is one accepted logical provider event.

## Acceptance pipeline

```text
resolve endpoint
→ enforce gross limits
→ verify signature against exact raw request bytes
→ verify replay window where supported
→ dedupe provider event
→ BEGIN
     insert WebhookDelivery
     insert OutboxEvent
   COMMIT
→ ACK provider
→ async processing
```

Provider ACK means durable responsibility accepted, not business processing completed.

## Status behavior

- unknown/revoked public ID: reject
- invalid signature/replay window: reject, no normal Delivery row
- transient DB acceptance failure: retryable non-2xx
- previously accepted duplicate with same event ID/hash: provider-success response, no new work
- valid but intentionally ignored event type: normally ACK success after provider-specific policy

Provider adapter may map the exact success/error codes required by that provider.

## Dedupe

Preferred uniqueness is stable Endpoint + provider event ID.

Same event ID + same payload hash is duplicate retry.

Same event ID + different payload hash is a security/integration anomaly.

Without provider event IDs, dedupe is explicitly best-effort.

## Payload retention

Delivery metadata and dedupe identity may outlive raw payload.

`payload_ref = NULL` is valid only after `payload_purged_at` records intentional purge.

## Execution

Accepted Delivery resolves/pins the active target BindingRevision once and later creates the canonical Execution.

Provider retries and internal Execution retries are separate concepts.
