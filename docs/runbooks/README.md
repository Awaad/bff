# Runbooks

Runbooks are operational procedures, not architecture essays.

Each exercised runbook must include owner, trigger/symptoms, customer impact, safety constraints, diagnosis, mitigation, recovery, verification, escalation, and `Last verified: YYYY-MM-DD`.

Initial required runbooks:

- Outbox/RabbitMQ backlog
- stuck/duplicate worker claims
- credential/KMS failure
- public runtime error spike
- webhook processing backlog
- notification delivery backlog
- scheduler lag/missed occurrences
- Sync destructive-change guard
- migration roll-forward/rollback
- privileged support/break-glass access

Do not mark a runbook verified until exercised in a representative environment.
