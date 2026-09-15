# Runbook: Public Runtime Error Spike

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger
Runtime 5xx/error-category rate or latency exceeds SLO.

## Safety
Do not expose raw upstream errors or secrets while diagnosing. Preserve synchronous runtime capacity from queue/backlog workloads.

## Diagnose
1. Break down by normalized error category/code.
2. Separate platform-wide from provider/tenant-specific failures.
3. Check PostgreSQL, KMS, DNS/network, and runtime saturation.
4. Sample traces via `execution_ref`/trace correlation.
5. Check recent deployment/config changes.

## Mitigate
Rollback/disable faulty deployment or provider capability, shed abusive traffic through supported rate controls, or quarantine a failing dependency. Avoid global Connection/Credential changes for tenant-local faults.

## Verify
Error rate/latency recovers and customer-visible histories remain coherent.
