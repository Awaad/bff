# Retained Schema Baselines

These files are immutable accepted snapshots used to verify historical migration
assets after the living desired schema evolves.

## `schema-v2.1.sql`

Exact canonical schema accepted for `0001_schema_baseline_v2_1`, including the
original `BEGIN` / `COMMIT` wrapper.

Do not update this file for later migrations. Evolve `docs/schema/schema.sql` and
add a new numbered migration instead.
