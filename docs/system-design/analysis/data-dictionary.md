# Data Dictionary - Backend as a Service Platform

| Entity | Key Fields | Description |
|--------|------------|-------------|
| Tenant | id, name, status, planTier | Top-level customer or organizational boundary |
| Project | id, tenantId, name, status, defaultRegion | Logical application workspace |
| Environment | id, projectId, name, stage, status | Environment such as dev, staging, or prod |
| CapabilityType | id, key, facadeVersion | Capability domain such as auth or storage |
| ProviderCatalogEntry | id, capabilityTypeId, providerKey, adapterVersion, certificationState | Supported provider-adapter offering |
| CapabilityBinding | id, environmentId, capabilityTypeId, providerCatalogEntryId, status | Active or pending provider selection |
| SwitchoverPlan | id, capabilityBindingId, targetProviderId, status, strategy | Planned provider migration workflow |
| SecretRef | id, environmentId, scope, providerKey, status | Reference to stored secret or credential material |
| AuthUser | id, projectId, externalUserId, status, primaryIdentityType | User identity record exposed by auth facade |
| SessionRecord | id, authUserId, sessionType, status, expiresAt | Session or token lifecycle record |
| DataNamespace | id, environmentId, schemaName, status | Data API schema boundary in Postgres |
| TableDefinition | id, dataNamespaceId, tableName, status, policyMode | Schema-managed table metadata |
| FileObject | id, environmentId, bucketKey, providerObjectRef, status | Storage facade file record |
| FunctionDefinition | id, environmentId, runtimeProfile, status, adapterBindingId | Function or job descriptor |
| ExecutionRecord | id, functionDefinitionId, invocationType, status, startedAt | Function or job execution history |
| EventChannel | id, environmentId, channelKey, status | Realtime or messaging namespace |
| Subscription | id, channelId, targetType, targetRef, status | Realtime or webhook-style subscription |
| UsageMeter | id, environmentId, capabilityTypeId, metricKey, value, measuredAt | Capability usage measurement |
| AuditLog | id, actorId, action, entityType, entityId, createdAt | Immutable operational audit trail |
