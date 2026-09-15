# Privileged Support Access

## Principles

Support access is explicit, bounded, least-privilege, and auditable.

A support session records original privileged actor, target Workspace/User context, reason/ticket where available, allowed scope, start time, and expiry.

Actions performed through support access preserve both the real support actor and the effective tenant context.

Impersonation must never make an event appear as though the customer performed it.

## Break-glass

If later introduced, break-glass access requires an explicit elevated event, reason, tight expiry, and additional monitoring.

## Secrets

Support tooling does not provide a general "show plaintext credential" function.

Credential diagnosis uses metadata and Execution correlation rather than secret disclosure.
