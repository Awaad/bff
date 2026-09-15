# Runbook: Notification Delivery Backlog

**Status:** Draft  
**Last verified:** Not yet verified

## Trigger
Pending NotificationDelivery age grows or time-sensitive deliveries approach expiration.

## Safety
Expiration overrides retry. Do not bulk resend deliveries with ambiguous provider acceptance.

## Diagnose
1. Break down by channel/provider/status.
2. Check provider health and callback ingestion.
3. Check queue age and worker capacity.
4. Identify messages nearing `expires_at`.

## Mitigate
Restore provider/worker capacity. Expire stale notifications according to policy. Do not cross-provider fail over when prior provider acceptance is indeterminate.

## Verify
Backlog age falls, expired messages are not delivered late, and dedupe prevents duplicate logical notifications.
