# Threat Model

## Highest-value assets

Customer API credentials, OAuth refresh tokens, signing secrets, tenant configuration, public mutation capabilities, runtime payloads, usage/billing integrity, and audit history.

## Main trust boundaries

1. public Framer site → runtime
2. Plugin/Dashboard → control plane
3. control/runtime → PostgreSQL
4. execution plane → KMS/credential resolver
5. runtime → customer-configured upstreams
6. dispatcher → RabbitMQ
7. provider → webhook ingress
8. platform support/operator → tenant state

## Major threats and controls

**Credential exfiltration:** write-only secrets, envelope encryption, execution-plane decrypt boundary, no decrypted Valkey cache, automatic redaction, no plaintext in AuditEvent.

**SSRF:** central HttpTransport, scheme/host/IP/DNS/redirect/TLS/byte/time policy, no caller-controlled arbitrary host.

**Cross-tenant access:** explicit `workspace_id`, tenant-aware composite FKs, authorization chokepoints, Project→Connection access rules, cross-workspace tests.

**Duplicate mutations:** caller/consumer idempotency, upstream idempotency propagation, deterministic Sync identity, schedule occurrence uniqueness, INDETERMINATE instead of blind retry.

**Queue duplication:** database truth, leases/fencing, idempotent consumers, durable dead-letter state.

**Webhook forgery/replay:** raw-body signature verification, versioned verification secrets, timestamp windows, provider event dedupe, rate/body limits.

**Public Binding abuse:** public IDs are not secrets; use schema validation, rate limits, origin/CORS browser controls, revocable IDs, admission checks.

**Privileged support abuse:** bounded support sessions, reason/ticket, dual actor attribution, least privilege, AuditEvent.

## Non-claims

CORS is not authentication. RabbitMQ is not exactly-once. Fencing cannot stop duplicate remote side effects. Public IDs are not bearer secrets.


## Framer project claim / reservation abuse

Threat: an authenticated tenant submits another customer's `framer_project_id` and attempts to reserve the globally unique active link, causing cross-tenant denial of service.

Controls:

- FramerProjectLink begins PENDING_VERIFICATION.
- Backend proves the supplied authorization/session has access to the exact claimed project before activation.
- Global active-project uniqueness is meaningful only after verification succeeds.
- Verification failures do not reserve the ACTIVE external project identity.
- E2E security tests attempt arbitrary cross-tenant project claims.
