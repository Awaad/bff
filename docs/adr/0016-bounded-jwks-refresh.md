# ADR 0016: Bounded JWKS refresh under unknown key IDs

**Status:** Accepted  
**Date:** 2026-09-17  
**Supersedes:** ADR 0015 only for the literal "immediate refresh" rule on unknown `kid`

## Context

ADR 0015 requires the authentication verifier to refresh JWKS immediately when an
unknown signing-key ID is encountered.

That rule was intended to minimize authentication disruption during normal provider
key rotation. However, an attacker controls the JWT header presented to the API and
can therefore send an unbounded stream of unique `kid` values.

PyJWT 2.14.0 introduced explicit security hardening for this condition. Its
`PyJWKClient` rate-limits forced JWKS refreshes caused by unknown key IDs through a
configurable cooldown. Disabling that cooldown would intentionally remove the
library's protection against remote key-ID refresh abuse.

## Decision

BFF keeps the rotation goal from ADR 0015 but replaces "always refresh immediately"
with a bounded refresh policy.

The WorkOS verifier:

- uses PyJWT 2.14.0 or a later explicitly reviewed compatible release;
- caches the provider JWKS for a bounded TTL;
- uses a non-zero unknown-`kid` refresh cooldown;
- permits PyJWT to force one refresh when the cooldown allows it;
- denies the token if no trusted matching key is available;
- never disables the cooldown merely to avoid a short rotation window;
- keeps JWKS request timeout bounded;
- accepts only explicitly allowlisted signing algorithms;
- never derives the JWKS URL, issuer, or accepted algorithm from token claims.

The initial defaults are:

```text
JWKS cache TTL:               300 seconds
JWKS request timeout:           5 seconds
unknown-kid refresh cooldown:  30 seconds
JWT clock leeway:              30 seconds
```

All values are runtime configuration and may be tightened after operational data.

## Availability tradeoff

A newly rotated signing key can be rejected for up to the remaining unknown-key
cooldown if it appears immediately after a recent JWKS fetch.

That short fail-closed interval is accepted in preference to allowing untrusted
`kid` values to trigger unbounded outbound requests.

Normal JWKS cache expiry and allowed forced refreshes still discover rotated keys.

## Consequences

- BFF does not undo PyJWT's unknown-key refresh abuse protection.
- Key rotation remains automatic but is explicitly bounded.
- Authentication fails closed during unresolved key rotation or JWKS outage.
- The WorkOS adapter contract and tests must distinguish "unknown key during
  cooldown" from a network/JWKS parsing failure.
