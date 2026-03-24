# Event Catalog - Backend as a Service Platform

| Event | Producer | Consumers | Description |
|-------|----------|-----------|-------------|
| tenant.project_created | Control Plane | Provisioning Workers, Audit | New project created |
| environment.provisioned | Provisioning Service | Control Plane, Reporting | Environment became ready |
| capability.binding_activated | Binding Service | Audit, Usage, SDK Config | Provider binding active |
| capability.switchover_requested | Control Plane | Migration Orchestrator | Provider change requested |
| capability.switchover_completed | Migration Orchestrator | Audit, Reporting, SDK Config | Capability migrated successfully |
| auth.user_created | Auth Facade | Audit, Event Streams | End-user identity created |
| session.issued | Auth Facade | Audit, Security Monitoring | Session or token created |
| data.schema_published | Data Service | Audit, Reporting | Schema change completed |
| file.object_created | Storage Facade | Audit, Usage | File stored through adapter |
| function.deployed | Function Facade | Execution Workers, Audit | Function definition activated |
| function.execution_completed | Execution Service | Reporting, Audit | Function or job finished |
| event.subscription_created | Realtime Facade | Delivery Workers | New event sink or subscriber configured |
| usage.threshold_exceeded | Usage Metering | Control Plane, Notification | Usage alert triggered |
| secret.rotated | Secret Service | Audit, Adapter Runtime | Credential updated |
