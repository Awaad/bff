# ADR-0004: Durable Transactional Notifications

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

Backend for Framer will produce customer-facing transactional and time-sensitive notifications from many domains, including Workspace/Membership, Billing, Usage, Credentials, Jobs, Sync, and security-related flows.

Sending provider messages directly inside producer-domain handlers creates reliability and coupling problems: durable notification intent can be lost after business commit, network I/O can leak into DB transactions, at-least-once events can duplicate messages, short-lived messages can arrive after expiry, provider acceptance may be ambiguous, and provider SDKs can spread across unrelated domains.

## Decision

Create a dedicated Notification domain with three reliability layers:

1. `Notification` — one logical customer message.
2. `NotificationDelivery` — one channel-specific delivery.
3. `NotificationDeliveryAttempt` — one concrete provider attempt.

Business domains emit durable events through the transactional outbox. They do not invoke email/SMS/provider APIs directly.

The Notification domain owns recipient resolution and snapshots, preferences, channels, immutable template versions, deterministic rendering, priority, `not_before`, `expires_at`, retry/backoff, provider routing, provider callbacks, and durable terminal state.

Logical notification creation is idempotent through stable dedupe keys.

Time-sensitive deadlines override transport retries.

Provider acceptance is distinct from confirmed delivery.

Automatic cross-provider failover is not considered safe when acceptance by the prior provider is indeterminate.

Customer/product notifications are separate from platform SRE/incident alerts.

Marketing/newsletter delivery is outside this domain.

## Consequences

### Positive

- Business state and notification delivery are decoupled without losing durable intent.
- At-least-once event delivery does not imply duplicate transactional email.
- Notification retries are deterministic.
- Short-lived messages do not arrive after expiration.
- Provider integrations can change without modifying business domains.
- Email and in-app notifications share one logical model.
- Customer-visible delivery state survives broker/DLQ cleanup.

### Negative

- Adds Notification, Delivery, Attempt, template-version, and preference state.
- Requires notification consumers/workers and provider callback handling.
- Recipient/content snapshots introduce PII retention responsibilities.
- Cross-provider failover requires provider-specific analysis rather than naive generic retry.

## Alternatives Considered

### Send directly from each business domain

Rejected because provider/network failure becomes coupled to business transactions and durable intent can be lost.

### Put email jobs directly on RabbitMQ without durable Notification state

Rejected because RabbitMQ is transport state, not product truth, and durable idempotency/history would be weak.

### Treat provider HTTP acceptance as delivered

Rejected because provider acceptance does not prove recipient delivery.

## Invariants

- Producer domains do not call notification providers directly.
- Transactional notification intent originates from durable business events/outbox.
- One logical Notification may have multiple channel Deliveries.
- Provider attempts never create duplicate logical Notifications.
- Expiration prevents stale retry delivery.
- Templates and destination snapshots do not silently change during retry.
- Required transactional/security notifications are not disabled by ordinary preferences.
- Product notification state remains durable independently of broker state.
