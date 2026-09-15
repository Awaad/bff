# Notification Contract

Layers:

- Notification — one logical customer message
- NotificationDelivery — one channel-specific delivery
- NotificationDeliveryAttempt — one provider attempt

Producer domains emit durable events/outbox entries; they never call email/SMS providers directly.

NotificationType defines supported channels, REQUIRED or CONFIGURABLE preference behavior, priority, template key/version behavior, expiry, and retry class.

Priority: CRITICAL, TRANSACTIONAL, NORMAL.

`not_before` and `expires_at` are semantic fields. Expiration overrides transport retry.

Recipient destination and rendered template version/content are snapshotted per Delivery. Retries do not silently switch address or template.

`PROVIDER_ACCEPTED` is distinct from `DELIVERED`.

Provider callbacks are authenticated and deduplicated.

Automatic cross-provider failover is not safe when previous acceptance is ambiguous.

Customer notifications are separate from SRE alerts. Marketing delivery is outside this domain.
