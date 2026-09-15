# Runbook: Database Migration Roll-Forward / Rollback

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger
Migration failure, incompatible application rollout, lock contention, or post-migration integrity regression.

## Safety
Prefer roll-forward for data/schema migrations. Never run destructive downgrade SQL without proving data compatibility and taking a recoverable backup/snapshot.

## Before migration
1. Confirm migration checksum/revision.
2. Run on disposable and staging databases.
3. Verify lock/runtime impact.
4. Verify backups/PITR.
5. Verify application compatibility window.

## Failure during migration
1. Stop further deploy progression.
2. Determine whether transaction rolled back completely.
3. If partially applied non-transactional work exists, follow migration-specific repair notes.
4. Do not hand-edit Alembic revision state without reconciling actual schema.

## Roll-forward
Ship a corrective migration when data shape cannot safely be downgraded.

## Rollback
Only use a tested downgrade for changes explicitly documented as reversible.

## Verify
Run schema checks, invariant tests, application health, and representative read/write E2E flows.
