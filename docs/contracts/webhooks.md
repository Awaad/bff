# Webhook Ingestion Contract

## Boundary

WebhookEndpoint is stable ingress identity. WebhookEndpointRevision is immutable verification/mapping configuration. WebhookDelivery is one accepted logical provider event.

## Acceptance pipeline

```text
resolve endpoint
→ enforce gross limits
→ verify signature against raw request bytes
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

## Dedupe

Preferred uniqueness is stable endpoint + provider event ID.

Same event ID + same payload hash is a duplicate retry.

Same event ID + different payload hash is a security/integration anomaly.

Without provider event IDs, dedupe is explicitly best-effort.

## Rejection

Unknown IDs, invalid signatures, oversized requests, or expired signed timestamps do not create ordinary WebhookDelivery rows.

## Execution

Accepted Delivery resolves/pins the active target BindingRevision once and later creates a canonical Execution.

Provider retries and Execution retries are separate concerns.
