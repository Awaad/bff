# Retained Database-role Baselines

These files preserve historical application-role policies for immutable migration
verification.

## `database-roles-v2.1.sql`

Exact role/grant policy accepted with Schema Baseline V2.1 and retained for
`0001_database_roles_v2_1.sql`.

Do not update this file when the current role policy evolves. Update
`docs/security/database-roles.sql` and the deployable `application_roles.sql`
instead.
