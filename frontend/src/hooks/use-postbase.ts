'use client';

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { useAuthStore } from '@/store/auth-store';
import type {
  PaginatedResponse,
  PostBaseBindingRead,
  PostBaseCapabilityHealthReport,
  PostBaseEnvironmentRead,
  PostBaseMigrationRead,
  PostBaseMigrationRetryResult,
  PostBaseProjectOverview,
  PostBaseProjectRead,
  PostBaseProviderCatalogRead,
  PostBaseSecretRead,
  PostBaseSecretRotateResult,
  PostBaseSwitchoverRead,
  PostBaseFunctionDeploymentEventRead,
  PostBaseFunctionRevisionRead,
  PostBaseFunctionScheduleRead,
  PostBaseUsageMeterRead,
  PostBaseWebhookDrainResult,
  PostBaseWebhookRecoveryResult,
  PostBaseChannelRead,
  PostBaseChannelPolicyTemplateRead,
  PostBaseWebhookEndpointRead,
  PostBaseAuditLogRead,
  PostBaseComplianceEvidenceBundleRead,
  PostBaseCertificationRunRead,
} from '@/types';

export function resolvePostBaseContextKey(tenantId: string | null | undefined): string {
  return tenantId ?? 'personal';
}

export interface PostBasePaginationParams {
  skip?: number;
  limit?: number;
}

const DEFAULT_POSTBASE_PAGINATION: Required<PostBasePaginationParams> = {
  skip: 0,
  limit: 25,
};

function normalizePaginationParams(params?: PostBasePaginationParams): Required<PostBasePaginationParams> {
  return {
    skip: params?.skip ?? DEFAULT_POSTBASE_PAGINATION.skip,
    limit: params?.limit ?? DEFAULT_POSTBASE_PAGINATION.limit,
  };
}

function updatePaginatedItems<T>(
  payload: PaginatedResponse<T> | undefined,
  updater: (items: T[]) => T[],
): PaginatedResponse<T> | undefined {
  if (!payload) return payload;
  const items = updater([...payload.items]);
  return {
    ...payload,
    items,
  };
}

export function usePostBaseProviderCatalog() {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'provider-catalog'],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseProviderCatalogRead>>('/provider-catalog');
      return response.data;
    },
    staleTime: 60_000,
  });
}

export function usePostBaseProjects(params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', tenantId, 'projects', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseProjectRead>>('/projects', { params: pagination });
      return response.data;
    },
    networkMode: 'offlineFirst',
    retry: 2,
    retryDelay: (attempt) => Math.min(1_000 * 2 ** attempt, 10_000),
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    staleTime: 30_000,
  });
}

export function usePostBaseEnvironments(projectId: string | undefined, params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', tenantId, 'projects', projectId, 'environments', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseEnvironmentRead>>(
        `/projects/${projectId}/environments`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
}

export function usePostBaseBindings(environmentId: string | undefined, params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'bindings', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseBindingRead>>(
        `/environments/${environmentId}/bindings`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(environmentId),
    staleTime: 15_000,
  });
}

export function usePostBaseSecrets(environmentId: string | undefined, params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'secrets', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseSecretRead>>(
        `/environments/${environmentId}/secrets`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(environmentId),
    staleTime: 15_000,
  });
}

export interface PostBaseSecretCreatePayload {
  name: string;
  provider_key: string;
  secret_kind: string;
  secret_value: string;
}

export interface PostBaseBindingCreatePayload {
  capability_key: string;
  provider_key: string;
  config_json?: Record<string, unknown>;
  secret_ref_ids?: string[];
  region?: string | null;
}

export interface PostBaseBindingStatusPayload {
  status: PostBaseBindingRead['status'];
  reason?: string;
}

export interface PostBaseSwitchoverCreatePayload {
  target_provider_key: string;
  strategy?: string;
  retirement_strategy?: string;
  canary_traffic_percent?: number;
  canary_health_checkpoint_count?: number;
  auto_abort_error_rate?: number;
  simulated_canary_error_rate?: number;
}

export function usePostBaseProjectOverview(projectId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'projects', projectId, 'overview'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseProjectOverview>(`/projects/${projectId}/overview`);
      return response.data;
    },
    enabled: Boolean(projectId),
    networkMode: 'offlineFirst',
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1_000 * 2 ** attempt, 10_000),
    refetchInterval: 20_000,
    refetchIntervalInBackground: true,
    staleTime: 15_000,
  });
}

export function usePostBaseProjectAudit(
  projectId: string | undefined,
  params?: { actor_user_id?: string; action?: string; resource?: string },
) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  return useQuery({
    queryKey: ['postbase', tenantId, 'projects', projectId, 'audit', params],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseAuditLogRead>>(`/projects/${projectId}/audit/query`, {
        params: {
          actor_user_id: params?.actor_user_id,
          action: params?.action,
          entity_type: params?.resource,
          limit: 50,
          skip: 0,
        },
      });
      return response.data;
    },
    enabled: Boolean(projectId),
    staleTime: 15_000,
  });
}

export function usePostBaseComplianceEvidence(environmentId: string | undefined, scope: 'privileged' | 'migration') {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'compliance', scope],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseComplianceEvidenceBundleRead>(
        `/environments/${environmentId}/compliance/evidence`,
        { params: { scope, export_format: 'json' } },
      );
      return response.data;
    },
    enabled: Boolean(environmentId),
    staleTime: 30_000,
  });
}

export function usePostBaseUsage(projectId: string | undefined, params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', tenantId, 'projects', projectId, 'usage', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseUsageMeterRead>>(
        `/projects/${projectId}/usage`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(projectId),
    staleTime: 15_000,
  });
}

export function usePostBaseCapabilityHealth(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseCapabilityHealthReport>(
        `/environments/${environmentId}/reports/capability-health`,
      );
      return response.data;
    },
    enabled: Boolean(environmentId),
    networkMode: 'offlineFirst',
    placeholderData: keepPreviousData,
    retry: 2,
    retryDelay: (attempt) => Math.min(1_000 * 2 ** attempt, 10_000),
    refetchInterval: 20_000,
    refetchIntervalInBackground: true,
    staleTime: 15_000,
  });
}

export function usePostBaseMigrations(environmentId: string | undefined, params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'migrations', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseMigrationRead>>(
        `/environments/${environmentId}/migrations`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(environmentId),
    staleTime: 10_000,
    refetchInterval: 10_000,
  });
}

export function useApplyPostBaseMigration(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'migrations', 0, 25] as const;

  return useMutation({
    mutationFn: async (migrationId: string) => {
      const response = await apiClient.post<PostBaseMigrationRead>(`/environments/${environmentId}/migrations/${migrationId}/apply`);
      return response.data;
    },
    onMutate: async (migrationId) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PaginatedResponse<PostBaseMigrationRead>>(queryKey);
      queryClient.setQueryData<PaginatedResponse<PostBaseMigrationRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === migrationId ? { ...item, status: 'pending' } : item))),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (migration) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseMigrationRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === migration.id ? migration : item))),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
    },
  });
}

export function useRetryPostBaseMigration(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'migrations', 0, 25] as const;

  return useMutation({
    mutationFn: async (migrationId: string) => {
      const response = await apiClient.post<PostBaseMigrationRetryResult>(
        `/environments/${environmentId}/migrations/${migrationId}/retry`,
      );
      return response.data;
    },
    onMutate: async (migrationId) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PaginatedResponse<PostBaseMigrationRead>>(queryKey);
      queryClient.setQueryData<PaginatedResponse<PostBaseMigrationRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === migrationId ? { ...item, status: 'pending' } : item))),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (result) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseMigrationRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === result.migration.id ? result.migration : item))),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
    },
  });
}

export function usePostBaseBindingSwitchovers(bindingId: string | undefined, params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', tenantId, 'bindings', bindingId, 'switchovers', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseSwitchoverRead>>(
        `/bindings/${bindingId}/switchovers`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(bindingId),
    staleTime: 10_000,
  });
}

export function useExecutePostBaseSwitchover(bindingId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'bindings', bindingId, 'switchovers', 0, 25] as const;

  return useMutation({
    mutationFn: async (switchoverId: string) => {
      const response = await apiClient.post<PostBaseSwitchoverRead>(`/switchovers/${switchoverId}/execute`);
      return response.data;
    },
    onMutate: async (switchoverId) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PaginatedResponse<PostBaseSwitchoverRead>>(queryKey);
      queryClient.setQueryData<PaginatedResponse<PostBaseSwitchoverRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === switchoverId ? { ...item, status: 'running' } : item))),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (switchover) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseSwitchoverRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === switchover.id ? switchover : item))),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'projects'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', undefined, 'bindings'] });
    },
  });
}

export function useRollbackPostBaseSwitchover(bindingId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'bindings', bindingId, 'switchovers', 0, 25] as const;
  return useMutation({
    mutationFn: async (switchoverId: string) => {
      const response = await apiClient.post<PostBaseSwitchoverRead>(`/switchovers/${switchoverId}/rollback`);
      return response.data;
    },
    onSuccess: async (switchover) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseSwitchoverRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === switchover.id ? switchover : item))),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'projects'] });
    },
  });
}

export function usePostBaseCertificationRuns(bindingId: string | undefined, params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);
  return useQuery({
    queryKey: ['postbase', tenantId, 'bindings', bindingId, 'certifications', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseCertificationRunRead>>(
        `/bindings/${bindingId}/certifications/runs`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(bindingId),
  });
}

export function useCreatePostBaseCertificationRun(bindingId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { switchover_id?: string; test_summary?: string }) => {
      const response = await apiClient.post<PostBaseCertificationRunRead>(`/bindings/${bindingId}/certifications/runs`, payload);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'bindings', bindingId, 'certifications'] });
    },
  });
}

export function useApprovePostBaseCertificationRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (runId: string) => {
      const response = await apiClient.post<PostBaseCertificationRunRead>(`/certifications/runs/${runId}/approve`);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase'] });
    },
  });
}

export function usePublishPostBaseCertificationRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (runId: string) => {
      const response = await apiClient.post<PostBaseCertificationRunRead>(`/certifications/runs/${runId}/publish`);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase'] });
    },
  });
}

export function useCreatePostBaseSecret(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PostBaseSecretCreatePayload) => {
      const response = await apiClient.post<PostBaseSecretRead>(`/environments/${environmentId}/secrets`, payload);
      return response.data;
    },
    onSuccess: async (secret) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseSecretRead>>(
        ['postbase', tenantId, 'environments', environmentId, 'secrets', 0, 25],
        (current) =>
          current
            ? { ...current, items: [secret, ...current.items], total: current.total + 1 }
            : current,
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'projects'] });
    },
  });
}

export function useRotatePostBaseSecret(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'secrets', 0, 25] as const;

  return useMutation({
    mutationFn: async ({ secretId, secretValue }: { secretId: string; secretValue: string }) => {
      const response = await apiClient.post<PostBaseSecretRotateResult>(
        `/environments/${environmentId}/secrets/${secretId}/rotate`,
        { secret_value: secretValue },
      );
      return response.data;
    },
    onMutate: async ({ secretId }) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PaginatedResponse<PostBaseSecretRead>>(queryKey);
      queryClient.setQueryData<PaginatedResponse<PostBaseSecretRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === secretId ? { ...item, status: 'rotating' } : item))),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (result) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseSecretRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === result.secret.id ? result.secret : item))),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
    },
  });
}

export function useDeactivatePostBaseSecret(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'secrets', 0, 25] as const;

  return useMutation({
    mutationFn: async (secretId: string) => {
      await apiClient.delete(`/environments/${environmentId}/secrets/${secretId}`);
      return secretId;
    },
    onMutate: async (secretId) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PaginatedResponse<PostBaseSecretRead>>(queryKey);
      queryClient.setQueryData<PaginatedResponse<PostBaseSecretRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === secretId ? { ...item, status: 'revoked' } : item))),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
    },
  });
}

export function useCreatePostBaseBinding(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PostBaseBindingCreatePayload) => {
      const response = await apiClient.post<PostBaseBindingRead>(`/environments/${environmentId}/bindings`, payload);
      return response.data;
    },
    onSuccess: async (binding) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseBindingRead>>(
        ['postbase', tenantId, 'environments', environmentId, 'bindings', 0, 25],
        (current) =>
          current
            ? { ...current, items: [binding, ...current.items], total: current.total + 1 }
            : current,
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'projects'] });
    },
  });
}

export function useUpdatePostBaseBindingStatus(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'bindings', 0, 25] as const;

  return useMutation({
    mutationFn: async ({ bindingId, payload }: { bindingId: string; payload: PostBaseBindingStatusPayload }) => {
      const response = await apiClient.post<PostBaseBindingRead>(`/bindings/${bindingId}/status`, payload);
      return response.data;
    },
    onMutate: async ({ bindingId, payload }) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PaginatedResponse<PostBaseBindingRead>>(queryKey);
      queryClient.setQueryData<PaginatedResponse<PostBaseBindingRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) =>
          item.id === bindingId ? { ...item, status: payload.status, last_transition_reason: payload.reason ?? 'manual_status_update' } : item,
        )),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (binding) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseBindingRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === binding.id ? binding : item))),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'projects'] });
    },
  });
}

export function useCreatePostBaseSwitchover(bindingId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PostBaseSwitchoverCreatePayload) => {
      const response = await apiClient.post<PostBaseSwitchoverRead>(`/bindings/${bindingId}/switchovers`, payload);
      return response.data;
    },
    onSuccess: async (switchover) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseSwitchoverRead>>(
        ['postbase', tenantId, 'bindings', bindingId, 'switchovers', 0, 25],
        (current) =>
          current
            ? { ...current, items: [switchover, ...current.items], total: current.total + 1 }
            : current,
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId] });
    },
  });
}

export function useDrainPostBaseWebhooks(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (limit: number = 200) => {
      const response = await apiClient.post<PostBaseWebhookDrainResult>(
        `/environments/${environmentId}/operations/webhooks/drain?limit=${limit}`,
      );
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'migrations'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId] });
    },
  });
}

export function useRecoverPostBaseWebhooks(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (limit: number = 200) => {
      const response = await apiClient.post<PostBaseWebhookRecoveryResult>(
        `/environments/${environmentId}/operations/webhooks/recover-exhausted?limit=${limit}`,
      );
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'migrations'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId] });
    },
  });
}

export function useReconcilePostBaseMigration(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'migrations', 0, 25] as const;

  return useMutation({
    mutationFn: async (migrationId: string) => {
      const response = await apiClient.post<PostBaseMigrationRead>(
        `/environments/${environmentId}/migrations/${migrationId}/reconcile`,
      );
      return response.data;
    },
    onSuccess: async (migration) => {
      queryClient.setQueryData<PaginatedResponse<PostBaseMigrationRead>>(queryKey, (current) =>
        updatePaginatedItems(current, (items) => items.map((item) => (item.id === migration.id ? migration : item))),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId] });
    },
  });
}

export function usePostBaseFunctionSchedules(functionId: string | undefined, params?: PostBasePaginationParams) {
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', 'functions', functionId, 'schedules', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseFunctionScheduleRead>>(
        `/functions/${functionId}/schedules`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(functionId),
    staleTime: 10_000,
  });
}

export function usePostBaseFunctionDeployments(functionId: string | undefined, params?: PostBasePaginationParams) {
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', 'functions', functionId, 'deployments', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseFunctionDeploymentEventRead>>(
        `/functions/${functionId}/deployments`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(functionId),
    staleTime: 10_000,
  });
}

export function usePostBaseFunctionRevisions(functionId: string | undefined, params?: PostBasePaginationParams) {
  const pagination = normalizePaginationParams(params);

  return useQuery({
    queryKey: ['postbase', 'functions', functionId, 'revisions', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseFunctionRevisionRead>>(
        `/functions/${functionId}/revisions`,
        { params: pagination },
      );
      return response.data;
    },
    enabled: Boolean(functionId),
    staleTime: 10_000,
  });
}


export function usePostBaseChannelPolicyTemplates() {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  return useQuery({
    queryKey: ['postbase', tenantId, 'events', 'channel-policy-templates'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseChannelPolicyTemplateRead[]>('/events/channel-policy-templates');
      return response.data;
    },
    staleTime: 60_000,
  });
}

export function usePostBaseChannels(environmentId: string | undefined, params?: PostBasePaginationParams) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const pagination = normalizePaginationParams(params);
  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'events', 'channels', pagination.skip, pagination.limit],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseChannelRead>>('/events/channels', { params: pagination });
      return response.data;
    },
    enabled: Boolean(environmentId),
  });
}

export function usePostBaseUpdateChannel() {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { channelId: number; policy_json?: Record<string, unknown>; description?: string; policy_template?: string }) => {
      const response = await apiClient.patch<PostBaseChannelRead>(`/events/channels/${payload.channelId}`, payload);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments'] });
    },
  });
}

export function usePostBaseWebhookEndpoints(environmentId: string | undefined, channelId?: number) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'events', 'webhook-endpoints', channelId],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseWebhookEndpointRead>>('/events/webhook-endpoints', {
        params: { channel_id: channelId, skip: 0, limit: 25 },
      });
      return response.data;
    },
    enabled: Boolean(environmentId),
  });
}

export function usePostBaseRotateWebhookEndpointSecret() {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { subscriptionId: number; new_secret: string; grace_window_seconds: number }) => {
      const response = await apiClient.post<PostBaseWebhookEndpointRead>(`/events/webhook-endpoints/${payload.subscriptionId}/rotate-secret`, payload);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments'] });
    },
  });
}
