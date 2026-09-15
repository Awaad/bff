# ADR-0001: Separate Control and Execution Planes

**Status:** Accepted

## Context

The product must support authoring/admin workflows and customer production execution without allowing control-plane failures, slow dashboard work, or worker backlog to starve synchronous runtime traffic. The codebase should remain modular rather than prematurely decomposed into microservices.

## Decision

Use a modular monorepo with strong domain boundaries and separate deployable control-plane and execution-plane runtimes from the beginning.

- Control plane: Python/FastAPI-oriented administration, authoring, versioning, billing/entitlements, scheduling/orchestration.
- Execution plane: TypeScript/Node-oriented runtime ingress, canonical operation execution engine, background execution workers, Framer/provider adapters.
- One primary relational source of truth initially.
- Control plane, runtime, and workers scale/fail independently.
- Infrastructure provider remains deliberately undecided.

## Consequences

- Production runtime can remain available during control-plane incidents.
- Runtime and workers can scale independently.
- The codebase pays some contract/versioning cost between Python and TypeScript.
- Deployment can target any suitable container/process platform later.

## Alternatives Considered

- Single Python service for everything: rejected because failure/scaling domains would be unnecessarily coupled.
- Microservices from day one: rejected as operationally premature.
- Cloudflare Workers as the complete execution platform: deferred; portability and workload constraints should be proven first.
