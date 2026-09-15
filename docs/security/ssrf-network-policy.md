# SSRF and Network Policy

All generic outbound HTTP execution flows through one central HttpTransport security boundary.

## URL and destination policy

- supported schemes only
- normalize host
- reject embedded credentials
- enforce port policy
- runtime caller cannot replace Connection destination
- bounded redirects with revalidation

## DNS/IP policy

Reject prohibited destinations including loopback, link-local, cloud metadata, private/internal ranges unless a future explicit private-network product allows them, multicast, and reserved ranges.

Revalidate redirect destinations and protect against DNS rebinding through validated resolution/connection strategy.

## Limits

Every request enforces connect timeout, overall deadline, request/response byte bounds where applicable, streaming byte accounting, and cancellation.

Customer configuration may become stricter than platform safety caps, never weaker.

TLS verification is mandatory; disabling certificate validation is not a feature.

Never log Authorization or credential-derived values.
