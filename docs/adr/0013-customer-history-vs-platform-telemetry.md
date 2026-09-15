# ADR-0013: Separate Customer History, Platform Telemetry, and Audit

- **Status:** Accepted
- **Date:** 2026-09-13

## Decision

Maintain three separate planes:

1. customer product history: Execution/Attempt, JobRun, WebhookDelivery, SyncRun, NotificationDelivery
2. platform telemetry: logs, traces, metrics, SRE alerts
3. AuditEvent: material control-plane/security accountability

Use OpenTelemetry for platform correlation.

## Invariants

- credentials/auth headers appear in none of these planes
- customer history stores normalized errors rather than raw stack traces
- SRE alerts are not customer Notification rows
