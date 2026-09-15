# Runbook: Credential / KMS Incident

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger

Elevated CREDENTIAL_UNAVAILABLE, KMS unwrap/decrypt failures, suspected compromise, or possible secret leakage into telemetry.

## Safety

Never print/copy plaintext credentials during diagnosis. Do not rotate/delete a customer's Credential without an authorized auditable action.

## Diagnose

1. Determine platform-wide vs single tenant/credential.
2. Check KMS dependency health.
3. Check Credential lifecycle and active SecretVersion metadata.
4. Check recent rotations/revocations.
5. Check redaction telemetry for suspected leaks.
6. Correlate ExecutionAttempts using IDs only.

## Mitigate

Platform KMS issue: restore dependency and fail closed while unavailable.

Single credential: disable if compromise is suspected, require rotation/re-auth, and notify via Notification domain where appropriate.

## Verify

No plaintext secret entered logs/audit, decrypt is limited to execution path, new executions use the intended SecretVersion, and material changes have AuditEvents.
