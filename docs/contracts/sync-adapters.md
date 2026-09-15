# Sync Adapter Contract

The Sync engine is provider-neutral and capability-driven. Framer is the first-class V1 adapter/UX specialization.

## Source adapter

Expected capabilities: discover schema, validate config, full reads, incremental reads/checkpoints where supported, stable identity extraction, tombstones where supported, and canonical typed normalization.

## Target adapter

Expected capabilities: discover schema, validate config, create/update/upsert, delete/lifecycle alternative, target inspection, deterministic identity where supported, field ownership, and publish/deploy where supported.

The core must never assume every target supports deterministic IDs, upsert, transactions, soft-delete, or publication.

## Identity

Generic SyncMapping stores provider-neutral identities, not Framer-specific columns.

## Safety

Incremental absence never means deletion. Absence-based delete requires a successful authoritative FULL scan. Large destructive deltas trigger review.

## Idempotency

Prefer deterministic/upsert identity, then upstream idempotency keys. Otherwise ambiguous writes become INDETERMINATE.

## Framer

Managed Collections are the recommended external→Framer mode where available because they provide stronger stable-ID/upsert behavior. Stable Framer field IDs are stored instead of display names.
