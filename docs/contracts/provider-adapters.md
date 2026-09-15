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
