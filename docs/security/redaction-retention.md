# Redaction and Retention

## Secrets

Never retained in plaintext: credential secrets, OAuth tokens, signing secrets, passwords, reset tokens, auth headers.

## Sensitive customer data

Runtime/webhook/sync payload data is retained only under explicit bounded policies.

## Product metadata

Status, IDs, timing, error categories, byte counts, and revision lineage may outlive payloads.

## Redaction

Sources include Credential-derived values, Operation fields marked sensitive, known secret headers, provider-specific secret fields, and security registries.

Redaction happens before durable payload storage.

Binary/stream bodies are normally not retained. Webhook raw payload may expire before Delivery metadata/dedupe identity. Idempotency/dedupe records must survive long enough for meaningful retry windows even if payloads are gone.

Audit receives only sanitized before/after/change metadata.

Purge is centralized and policy-driven.
