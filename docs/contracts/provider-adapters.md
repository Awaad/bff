# Provider Adapter Contract

Provider adapters translate provider-specific behavior into canonical platform contracts without bypassing central safety.

Rules:

1. Native providers do not implement unrestricted parallel HTTP stacks.
2. Outbound calls use central HttpTransport or an approved equivalent enforcing the same policy.
3. Provider SDKs stay behind adapters.
4. Provider errors map to canonical error categories/codes.
5. Provider configuration is typed and schema-versioned.
6. Provider code receives only required credential material.
7. Provider metadata cannot override tenant/security scope.

Provider-native Operations compile into the same canonical executable representation as generic HTTP Operations.

Adapters declare compatible Credential schemes and capabilities such as upstream idempotency, pagination cursor, deterministic target IDs, publish/deploy, webhooks, and OAuth refresh.

Webhook adapters may additionally define raw signature verification, signed timestamp rules, event ID extraction, and ACK semantics.

## Initial generic HTTP Connection contract

The first registered Connection provider is `generic_http`, definition schema
version `1`. Its non-secret configuration is an exact object:

```json
{
  "base_url": "https://api.example.com/v1"
}
```

`base_url` must use HTTPS, include a host, and contain no username, password,
query, or fragment. Draft writes and publication lowercase the scheme and host,
remove the default HTTPS port, preserve the supplied path, and remove its trailing slash.
Publication serializes the canonical object with deterministic JSON and hashes
those bytes with SHA-256. Unknown fields are rejected before draft storage.

This publication check defines configuration identity; it is not the runtime
SSRF decision. The central transport still resolves and validates the final
destination for every outbound request, including redirects and DNS changes.

Credential references, headers carrying authentication material, and secret
values are not valid Connection configuration. They belong to versioned
Credential state and are injected only at execution time.
