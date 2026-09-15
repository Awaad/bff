# Current Engineering State

## Status

Architecture and schema design are complete enough to begin implementation.

## Frozen

- aggregate design
- cross-aggregate invariants
- PostgreSQL baseline schema
- migration policy
- architecture/context specs
- runtime/queue/error/adapter contracts
- security specs
- ADRs through 0013

## Not yet implemented

Documentation is not implementation. No claim yet that migrations, APIs, runtime, queues, encryption, Plugin, Dashboard, or E2E tests exist.

## First build target

1. User/Workspace
2. Project
3. Connection
4. Credential + encrypted SecretVersion
5. Operation + OperationVersion
6. Binding + BindingRevision compilation
7. PUBLIC runtime endpoint
8. Execution + Attempt
9. execution history
10. AuditEvent
11. E2E test

Then add idempotent Actions, outbox/RabbitMQ, Jobs, Webhooks, Notifications, and Sync.

## Rules

- no direct cross-domain repository imports
- no raw provider SDKs inside business domains
- no secrets in queue messages/logs
- no broker-as-truth
- no "latest version" runtime joins for immutable historical execution
- reliability paths must be tested under duplicate delivery and failure
