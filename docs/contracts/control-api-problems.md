# Control API Problem Contract

Public API failures use RFC 9457 Problem Details with:

```text
Content-Type: application/problem+json
```

Clients branch on stable `code` or `type`, never on `title` or `detail`.

Initial codes:

| Code | HTTP | Retryable | Meaning |
| --- | ---: | --- | --- |
| `AUTH_INVALID_CREDENTIALS` | 401 | unspecified | Authentication evidence or local admission is invalid |
| `AUTH_EMAIL_VERIFICATION_REQUIRED` | 403 | no | First provisioning requires verified provider email |
| `AUTH_ACCOUNT_LINK_REQUIRED` | 409 | no | Explicit identity linking is required |
| `AUTH_PROVIDER_UNAVAILABLE` | 503 | yes | Authentication provider/profile service is unavailable |
| `REQUEST_VALIDATION_FAILED` | 422 | no | Request validation failed |
| `REQUEST_NOT_FOUND` | 404 | no | Endpoint was not found |
| `REQUEST_METHOD_NOT_ALLOWED` | 405 | no | Route exists but method is unsupported |
| `REQUEST_REJECTED` | varies | unspecified | Generic HTTP rejection |
| `INTERNAL_ERROR` | 500 | unspecified | Unexpected server failure |

Validation issues may contain:

```json
{
  "pointer": "#/body/name",
  "code": "REQUIRED",
  "detail": "Field is required."
}
```

Initial issue codes are `REQUIRED`, `INVALID_JSON`, and `INVALID_VALUE`.

Every response carries a server-generated `X-Request-ID`. Problem responses repeat
it as `request_id` and `instance = urn:uuid:<request_id>`.

Problem bodies never contain bearer/access/refresh tokens, provider response
bodies, SQL/database errors, stack traces, request bodies, raw auth/cookie headers,
or secret material.
