# Request Context and Correlation

At request ingress BFF creates:

```text
request_id: UUIDv7
trace_id: optional OpenTelemetry trace ID
started_at: UTC timestamp
```

The API returns `X-Request-ID` on responses.

Access logs use structured fields only:

```text
request_id
trace_id
method
route
status_code
duration_ms
```

They do not record raw unmatched paths, query strings, request/response bodies,
Authorization/Cookie headers, User-Agent strings, or IP addresses.

When an active OpenTelemetry span exists, middleware captures its trace ID and adds
`bff.request.id` to that span.

Application services that persist provenance receive correlation explicitly.
Background workers reconstruct operation context from durable message metadata,
not from HTTP ContextVar state.
