# Credential Handling

Model:

```text
Credential
├── CredentialRevision
├── CredentialSecretVersion
└── OAuthTokenState
```

Credential is stable auth identity. CredentialRevision is immutable auth semantics. CredentialSecretVersion is immutable encrypted material.

Secrets are write-only after submission.

## Envelope encryption

1. generate random DEK
2. encrypt secret with authenticated encryption
3. wrap DEK using external KMS abstraction
4. persist ciphertext, wrapped DEK, algorithm/version metadata

Database compromise alone must not reveal plaintext.

## Decryption boundary

Execution plane decrypts only at the last responsible moment. Control plane does not routinely decrypt. Decrypted secrets are never stored in Valkey/distributed cache.

## Rotation

Secret versions are immutable and may move through PENDING, ACTIVE, RETIRING, REVOKED, DESTROYED.

Routine rotation does not require Binding republish. ExecutionAttempt records the exact SecretVersion used.

## OAuth

Durable refresh/root secrets are encrypted. Short-lived mutable access-token state may use encrypted OAuthTokenState. Refresh requires concurrency control.

## Redaction

Credential-derived values are automatically registered for redaction across logs, traces, retained payloads, audit, and diagnostics.

No automatic credential fallback.
