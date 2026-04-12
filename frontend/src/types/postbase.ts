export type ParityStatus = 'implemented' | 'partial' | 'planned';

export interface PostBaseProjectRead {
  id: string;
  tenant_id: string;
  name: string;
  slug: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PostBaseEnvironmentRead {
  id: string;
  project_id: string;
  name: string;
  slug: string;
  stage: 'development' | 'staging' | 'production';
  region_preference: string | null;
  status: 'active' | 'degraded' | 'inactive';
  readiness_state: 'ready' | 'degraded' | 'not_ready' | 'validating';
  readiness_detail: string;
  last_validated_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PostBaseBindingRead {
  id: string;
  environment_id: string;
  capability_key: string;
  provider_key: string;
  adapter_version: string;
  status:
    | 'pending_validation'
    | 'active'
    | 'deprecated'
    | 'retired'
    | 'failed'
    | 'disabled';
  readiness_detail: string;
  linked_secret_ref_ids: string[];
  supersedes_binding_id: string | null;
  region: string | null;
  config_json: Record<string, unknown>;
}

export interface PostBaseMigrationRead {
  id: string;
  environment_id: string;
  namespace_id: string;
  table_definition_id: string | null;
  version: string;
  status: 'pending' | 'applied' | 'failed';
  reconciliation_status: 'pending_apply' | 'in_sync' | 'drifted';
  drift_severity?: string | null;
  affected_entities?: string[];
  reconcile_attempt_count?: number;
  reconcile_error_text?: string | null;
  last_reconciled_at?: string | null;
  applied_sql: string;
  created_at: string;
}

export interface PostBaseMigrationRetryResult {
  migration: PostBaseMigrationRead;
  rollback_sql: string;
  rollback_status: string;
}

export interface PostBaseSecretRead {
  id: string;
  environment_id: string;
  name: string;
  provider_key: string;
  secret_kind: string;
  version?: number;
  is_active_version?: boolean;
  status: string;
  rotated_at?: string | null;
  expires_at?: string | null;
  last_four: string;
  created_at: string;
  updated_at: string;
}

export interface PostBaseSecretRotateResult {
  secret: PostBaseSecretRead;
  impacted_binding_ids: string[];
  rollback_ready: boolean;
}

export interface PostBaseProviderCatalogRead {
  id: string;
  capability_key: string;
  provider_key: string;
  adapter_version: string;
  certification_state: string;
  metadata_json: Record<string, unknown>;
}

export interface PostBaseUsageMeterRead {
  id: string;
  environment_id: string;
  capability_key: string;
  metric_key: string;
  value: number;
  measured_at: string;
}

export interface PostBaseSwitchoverRead {
  id: string;
  capability_binding_id: string;
  target_provider_catalog_entry_id: string;
  strategy: string;
  retirement_strategy?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  execution_detail: string;
  execution_state_json?: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
}

export interface PostBaseProviderHealthRead {
  capability_key: string;
  provider_key: string;
  adapter_version: string;
  ready: boolean;
  detail: string;
}

export interface PostBaseCapabilityHealthReport {
  environment_id: string;
  bindings: PostBaseBindingRead[];
  provider_health: PostBaseProviderHealthRead[];
  overall_ready: boolean;
  degraded_capabilities: string[];
}

export interface PostBaseEnvironmentOverview {
  environment_id: string;
  stage: 'development' | 'staging' | 'production';
  status: 'active' | 'degraded' | 'inactive';
  readiness_state: 'ready' | 'degraded' | 'not_ready' | 'validating';
  readiness_detail: string;
  active_bindings: number;
  degraded_bindings: number;
  recent_switchovers: number;
  pending_migrations: number;
  secret_count: number;
  key_count: number;
  usage_points_total: number;
  recent_audit_events: number;
}

export interface PostBaseProjectOverview {
  project_id: string;
  environment_count: number;
  active_environment_count: number;
  active_bindings: number;
  degraded_bindings: number;
  secret_count: number;
  usage_points_total: number;
  recent_audit_events: number;
  environments: PostBaseEnvironmentOverview[];
}


export interface PostBaseOperationsChecklistItem {
  item: string;
  completed: boolean;
}

export interface PostBaseWebhookDrainResult {
  triggered: boolean;
  drained_count: number;
  reason: string;
  checklist: PostBaseOperationsChecklistItem[];
}

export interface PostBaseWebhookRecoveryResult {
  scanned_failed_jobs: number;
  requeued_jobs: number;
  exhausted_job_ids: string[];
  skipped_jobs: number;
  skipped_job_ids: string[];
  reasons: Record<string, number>;
}

export interface PostBaseErrorDetail {
  field?: string | null;
  message: string;
  context?: Record<string, unknown> | null;
}

export interface PostBaseErrorEnvelope {
  code: string;
  message: string;
  details: PostBaseErrorDetail[];
}

export interface PostBaseErrorResponse {
  error: PostBaseErrorEnvelope;
}

export interface PostBaseCapabilityStatusResponse {
  status: 'ready' | 'degraded' | 'error';
  reason: string;
  provider_key: string | null;
}

export interface PostBaseFunctionExecutionRead {
  id: number;
  function_definition_id: number;
  invocation_type: string;
  idempotency_key: string | null;
  correlation_id: string;
  replay_of_execution_id: number | null;
  retry_of_execution_id: number | null;
  retry_count: number;
  timeout_ms: number | null;
  cancel_requested: boolean;
  status: string;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  error_text: string;
  started_at: string;
  completed_at: string | null;
  log_excerpt: string;
}

export interface PostBaseEventDeliveryRead {
  id: number;
  channel_id: number;
  subscription_id: number | null;
  event_name: string;
  status: string;
  attempt_count: number;
  delivered_at: string | null;
  error_text: string;
  payload_json: Record<string, unknown>;
}
