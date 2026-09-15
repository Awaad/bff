# Runbooks

Runbooks are operational procedures, not architecture essays.

Every exercised runbook must carry `Last verified: YYYY-MM-DD`.

Initial required set:

- `outbox-backlog.md` — Outbox/RabbitMQ backlog
- `worker-claims.md` — stuck/duplicate worker claims
- `credential-incident.md` — Credential/KMS failure
- `runtime-error-spike.md` — public runtime error spike
- `webhook-backlog.md` — webhook processing backlog
- `notification-backlog.md` — notification delivery backlog
- `scheduler-lag.md` — scheduler lag/missed occurrences
- `sync-delete-guard.md` — Sync destructive-change guard
- `migration-rollback.md` — migration roll-forward/rollback
- `support-break-glass.md` — privileged support/break-glass access

Do not mark a runbook verified until it has been exercised in a representative environment.
