# Deployment Specification

Cloud/provider selection is intentionally deferred.

## Deployable units

- control-plane API
- public runtime API
- background workers
- scheduler
- outbox dispatcher
- notification processor
- webhook processor
- sync worker
- dashboard frontend
- Framer Plugin build

Processes/images may initially be shared, but scaling and failure domains must remain separable.

## Required stateful services

- PostgreSQL
- RabbitMQ
- Valkey/Redis
- KMS-compatible wrapping service
- object storage when larger retained artifacts are required
- OpenTelemetry collector/backend

## Availability

- control-plane outage must not automatically take runtime down
- queue backlog must not consume synchronous runtime capacity
- scheduler and outbox dispatcher support multiple replicas
- workers assume redelivery
- Valkey loss is degradable, not corrupting
- PostgreSQL remains authoritative

## Networking

Runtime/worker egress follows `security/ssrf-network-policy.md`.

Credential/KMS permissions should be narrower than normal control-plane access.

## Deferred

Cloud provider, region topology, SKU sizing, autoscaling thresholds, CDN/WAF vendor, and telemetry vendor.

Terraform/OpenTofu is the likely IaC family, but is not yet frozen.
