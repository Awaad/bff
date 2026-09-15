# Product Surfaces

## Framer Plugin

Project-local authoring: connect the current Framer project, create/browse simple Connections and Operations, bind Queries/Actions/forms/components, test/preview, author Framer-specific Sync, and surface project-local errors.

The Plugin is not the full SaaS administration surface.

## Web Dashboard

Full control plane: Workspace/team/billing, multi-project admin, credentials, advanced configuration, publication/policies, jobs/schedules/webhooks/sync, usage, audit, and full execution history/reconciliation.

## Customer Operations

Durable execution/attempt history, normalized errors, sanitized payloads, retry/replay, Job/Webhook/Sync histories, item-level Sync failures, and durable dead-letter state.

## Internal Platform Ops

Health, queues, database/cache, traces, incidents, quarantine/pause, feature flags, and privileged support access.

## Canonical configuration

Each concept has one authoritative backend model. Multiple surfaces may edit it, but never maintain independent copies of truth.
