# Runtime API Contract

## Route

Conceptually: `/runtime/v1/b/{public_binding_id}`.

The ID is routing identity, not authentication.

## Admission

Semantically:

1. resolve public ID
2. Binding ACTIVE and PUBLIC
3. Workspace ACTIVE
4. Project ACTIVE
5. resolve active BindingRevision once
6. Connection ACTIVE
7. Credential ACTIVE and usable
8. Project may use Connection
9. Entitlements/quota/rate policy allow
10. validate exposed input
11. create/resolve Execution and Idempotency state
12. execute immutable compiled artifact

## QUERY

QUERY may expose only READ OperationVersion. Caching is allowed only when OperationVersion is cache-eligible and Binding policy enables it.

## ACTION

ACTION may expose READ or WRITE. Idempotency policy: DISABLED, SUPPORTED, or REQUIRED.

Same Binding + same key + same canonical request reuses the original Execution. Same key with a different request is rejected.

## Bodies

Request modes: NONE, JSON, FORM_URLENCODED, MULTIPART, RAW.

Response modes: JSON, TEXT, BINARY, STREAM.

Caller cannot choose arbitrary Connection, Credential, host, method, or privileged headers.

## Pinning

Once accepted, the request stays pinned to the resolved BindingRevision even if a new revision is published concurrently.
