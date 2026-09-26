# Architecture Decision Records

ADRs capture accepted decisions whose reversal would affect multiple layers, migrations, or operational contracts.

Accepted ADRs are immutable. Supersede with a new ADR rather than editing the old decision into a different one.

Current series:

- 0001 control/execution planes
- 0002 immutable versioned runtime configuration
- 0003 at-least-once + durable idempotency
- 0004 durable transactional notifications
- 0005 transactional outbox + RabbitMQ
- 0006 HA scheduler + durable occurrences
- 0007 durable webhook ingestion before ACK
- 0008 provider-neutral Sync engine
- 0009 immutable audit ledger
- 0010 canonical TypeScript executor
- 0011 Billing/Entitlements/Usage separation
- 0012 versioned envelope-encrypted credentials
- 0013 customer history vs platform telemetry
- 0014 provider-neutral control-plane identity
- 0015 durable control-plane session admission
- 0016 bounded JWKS refresh under unknown key IDs
- 0017 public-client login and local session provisioning
- 0018 structured API problem details
- 0019 request context and transport middleware
- 0020 Workspace authorization boundary
- 0021 Project authorization boundary
- 0022 Connection authorization and Project-access boundary