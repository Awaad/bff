# Credential Handling — V2.1

## Model

`Credential` is stable auth identity. `CredentialRevision` is immutable auth-application semantics. `CredentialSecretVersion` is immutable secret material with lifecycle metadata.

## First-class no-auth scheme

Unauthenticated upstreams use a first-class Credential with `auth_scheme = NONE`.

A NONE Credential:

- has an immutable CredentialRevision with empty authentication configuration;
- has no CredentialSecretVersion;
- injects no authentication headers;
- requires no KMS access.

This is intentional rather than a synthetic workaround. Keeping a Credential identity for NONE preserves one uniform non-null BindingRevision/Execution lineage shape and avoids reopening nullable credential-composition semantics.

The product UI presents it simply as **No authentication**.

## Secret handling

Secret material is write-only after submission, envelope encrypted, and decrypted only in the execution context at the last responsible moment. Plaintext secret material must never enter PostgreSQL, RabbitMQ, Valkey, logs, traces, audit, or retained execution payloads.
