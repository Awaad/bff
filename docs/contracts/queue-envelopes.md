# Queue Envelope Contract

RabbitMQ is transport, not truth. Messages are small, versioned, and contain IDs/references rather than secrets or large payloads.

## Generic shape

```json
{
  "message_id": "uuidv7",
  "type": "execution.requested",
  "version": 1,
  "occurred_at": "RFC3339",
  "workspace_id": "uuid",
  "correlation_id": "uuid",
  "payload": { "execution_id": "uuid" }
}
```

## Outbox

```text
BEGIN
  mutate business state
  insert OutboxEvent
COMMIT
```

Dispatcher publishes and marks published after broker confirm. A crash after broker acceptance but before DB acknowledgement may duplicate publication. This is expected.

## Consumer

Durably complete domain processing before acknowledging the broker.

Use stronger domain uniqueness where available: schedule occurrence identity, provider webhook event ID, Notification dedupe key, primary Webhook Execution uniqueness, UsageEvent dedupe key.

Broker retry and business-operation retry are separate concepts.

Broker DLQ is not customer-visible truth; domain state carries DEAD_LETTERED/FAILED.

No global ordering guarantee.
