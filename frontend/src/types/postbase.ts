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
  applied_sql: string;
  created_at: string;
}

export interface PostBaseSecretRead {
  id: string;
  environment_id: string;
  name: string;
  provider_key: string;
  secret_kind: string;
  status: string;
  last_four: string;
  created_at: string;
  updated_at: string;
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
  status: 'pending' | 'running' | 'completed' | 'failed';
  execution_detail: string;
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
