# ADR-0012: Versioned Credentials with Envelope Encryption

- **Status:** Accepted
- **Date:** 2026-09-13

## Decision

Use Credential as stable auth identity, CredentialRevision as immutable application semantics, and CredentialSecretVersion as immutable encrypted secret material.

Use envelope encryption with externally wrapped DEKs.

BindingRevision pins Credential + CredentialRevision, not SecretVersion.

Runtime resolves the current usable SecretVersion at the last responsible moment.

## Invariants

- write-only secrets
- no plaintext/decrypted distributed cache
- historical revoked secret versions are never resurrected during replay
- ciphertext is not mutated in place
