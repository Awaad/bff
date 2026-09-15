# Runbook: Sync Destructive-Change Guard

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger

A SyncRun enters REQUIRES_CONFIRMATION because proposed destructive changes exceed safety policy.

## Safety

Do not bypass the guard through direct target/API/database edits.

## Diagnose

1. Confirm the source scan completed authoritatively.
2. Compare previous mapped count with current source count.
3. Inspect source filters/credentials/pagination for accidental truncation.
4. Review SyncRevision changes since the last successful full run.
5. Sample records proposed for deletion/soft-delete.

## Resolution

- confirm destructive action if data is correct and authorization permits
- choose KEEP if source loss is temporary/incorrect
- fix source/config and run another FULL dry-run

All manual confirmation/relink decisions must produce AuditEvents.
