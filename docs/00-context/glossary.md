# Glossary

**Workspace** — tenant ownership boundary.

**Project** — Backend for Framer project identity; Framer-first but internally platform-neutral.

**Connection** — logical external account/environment boundary.

**ConnectionRevision** — immutable destination/config semantics.

**Credential** — stable outbound auth identity.

**CredentialRevision** — immutable auth application semantics.

**CredentialSecretVersion** — immutable encrypted secret material.

**Operation** — stable semantic backend capability.

**OperationVersion** — immutable executable contract describing what happens.

**Binding** — stable Project-local capability exposure identity.

**BindingRevision** — immutable published composition of Operation/Connection/Credential plus exposure policy.

**PUBLIC Binding** — publicly routable runtime capability.

**INTERNAL Binding** — reusable capability with no public endpoint, used by Jobs/Webhooks/Sync.

**Execution** — one logical invocation.

**ExecutionAttempt** — one concrete processing attempt.

**JobDefinition** — stable schedule intent.

**JobRun** — one durable scheduled occurrence.

**WebhookEndpoint** — stable inbound webhook identity.

**WebhookDelivery** — one accepted logical provider event.

**SyncDefinition** — stable identity for one directional sync.

**SyncRevision** — immutable sync configuration.

**SyncMapping** — durable source↔target identity.

**Notification** — one logical product message.

**OutboxEvent** — durable publication intent committed with business state.

**AuditEvent** — append-only accountability record.

**INDETERMINATE** — remote side effect may have happened but cannot be safely proven.
