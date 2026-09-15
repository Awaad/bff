# Error Model

## Shape

```json
{
  "error": {
    "code": "CREDENTIAL_UNAVAILABLE",
    "category": "AUTH",
    "message": "The configured credential is unavailable.",
    "retryable": false,
    "execution_ref": "..."
  }
}
```

## Categories

VALIDATION, POLICY, AUTH, UPSTREAM_4XX, UPSTREAM_RATE_LIMIT, UPSTREAM_5XX, UPSTREAM_TIMEOUT, NETWORK, TRANSFORM, CONFIGURATION, PLATFORM, CANCELLED, UNKNOWN.

## Example stable codes

INPUT_INVALID, ORIGIN_NOT_ALLOWED, RATE_LIMITED, ENTITLEMENT_DENIED, CREDENTIAL_UNAVAILABLE, CREDENTIAL_REAUTH_REQUIRED, UPSTREAM_TIMEOUT, UPSTREAM_RATE_LIMITED, UPSTREAM_RESPONSE_INVALID, TRANSFORM_FAILED, SCHEMA_DRIFT, IDEMPOTENCY_KEY_REUSED, EXECUTION_INDETERMINATE, BINDING_DISABLED, PROJECT_DISABLED.

Retryability is not inferred from category alone; it also depends on effect, idempotency safety, ambiguity, and attempt limits.

Customer-facing errors never expose secrets, auth headers, internal stack traces, or private-network details.

`INDETERMINATE` is a first-class terminal outcome, not FAILED.


## Public correlation identifier

Public runtime errors return `execution_ref`, backed by `executions.public_execution_ref`.

The internal UUIDv7 Execution primary key is not returned merely for correlation. UUIDv7 is time-ordered and can reveal approximate creation time.

Authenticated internal/customer operations APIs may use internal IDs according to authorization policy.
