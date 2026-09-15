# Launch Strategy

## Production readiness

Core 0–4 must work together and be tested meaningfully before broad production access.

Required confidence includes schema invariant tests, real E2E runtime tests, credential leakage tests, idempotency/retry tests, broker redelivery tests, failure/recovery tests, observability, usage accounting, and runbooks.

## Launch A — controlled production

Founding/free production access after the safety and reliability threshold. Goals: understand traffic, support load, abuse, cost, quota behavior, and incident response.

## Launch B — paid availability

Paid availability follows evidence from controlled production. Before it: billing lifecycle understood, entitlements enforced, runtime cost understood, metering trusted, support paths and critical runbooks exist, and retention policy is defined.

Capabilities may exist earlier behind internal/workspace/project flags.
