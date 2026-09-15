# Pricing / Entitlement Model

Exact prices and allowances are intentionally deferred.

- Billing = what was purchased
- Entitlements = what is allowed
- Usage = what was consumed

Do not store `plan=PRO` or `is_pro` on Workspace or Project.

Billing belongs to Workspace. Entitlements may be Workspace- or Project-scoped. Usage is measured primarily per Project and aggregated to Workspace.

Entitlement sources include subscription, add-on, founding access, promotion, manual grant, and enterprise contract.

UsageEvent is append-only and deduplicated. UsageBucket is an aggregate. Valkey quota counters are non-authoritative.

Enforcement classes: HARD, THROTTLE, SOFT/OVERAGE, LIFECYCLE.

Runtime reasons in typed entitlement keys, never marketing plan names.
