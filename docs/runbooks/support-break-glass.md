# Runbook: Privileged Support / Break-Glass Access

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger
Authorized support investigation requires tenant-scoped privileged access, or a declared incident requires emergency elevation.

## Safety
Never impersonate a customer invisibly. Never retrieve plaintext credentials. Every session requires a reason and bounded scope/expiry.

## Procedure
1. Confirm support authorization/ticket.
2. Create SupportSession with target Workspace, scope, reason, and expiry.
3. Use only the minimum permitted capabilities.
4. Ensure all material actions reference the SupportSession in AuditEvent.
5. End the session when work completes.

## Break glass
Emergency elevation requires explicit incident reference, short expiry, and post-incident review.

## Verify
Audit history contains real privileged actor plus effective tenant context; session is expired/ended; no secrets were exposed.
