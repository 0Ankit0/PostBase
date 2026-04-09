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
  PostBaseUsageMeterRead,
  PostBaseWebhookDrainResult,
  PostBaseWebhookRecoveryResult,
} from '@/types';

export function resolvePostBaseContextKey(tenantId: string | null | undefined): string {
  return tenantId ?? 'personal';
}

export function usePostBaseProviderCatalog() {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'provider-catalog'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseProviderCatalogRead[]>('/provider-catalog');
      return response.data;
    },
    staleTime: 60_000,
  });
}

export function usePostBaseProjects() {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'projects'],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseProjectRead>>('/projects');
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

export function usePostBaseEnvironments(projectId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'projects', projectId, 'environments'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseEnvironmentRead[]>(`/projects/${projectId}/environments`);
      return response.data;
    },
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
}

export function usePostBaseBindings(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'bindings'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseBindingRead[]>(`/environments/${environmentId}/bindings`);
      return response.data;
    },
    enabled: Boolean(environmentId),
    staleTime: 15_000,
  });
}

export function usePostBaseSecrets(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'secrets'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseSecretRead[]>(`/environments/${environmentId}/secrets`);
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

export function usePostBaseUsage(projectId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'projects', projectId, 'usage'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseUsageMeterRead[]>(`/projects/${projectId}/usage`);
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

export function usePostBaseMigrations(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'environments', environmentId, 'migrations'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseMigrationRead[]>(`/environments/${environmentId}/migrations`);
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
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'migrations'] as const;

  return useMutation({
    mutationFn: async (migrationId: string) => {
      const response = await apiClient.post<PostBaseMigrationRead>(`/environments/${environmentId}/migrations/${migrationId}/apply`);
      return response.data;
    },
    onMutate: async (migrationId) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PostBaseMigrationRead[]>(queryKey);
      queryClient.setQueryData<PostBaseMigrationRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === migrationId ? { ...item, status: 'pending' } : item)),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (migration) => {
      queryClient.setQueryData<PostBaseMigrationRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === migration.id ? migration : item)),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
    },
  });
}

export function useRetryPostBaseMigration(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'migrations'] as const;

  return useMutation({
    mutationFn: async (migrationId: string) => {
      const response = await apiClient.post<PostBaseMigrationRetryResult>(
        `/environments/${environmentId}/migrations/${migrationId}/retry`,
      );
      return response.data;
    },
    onMutate: async (migrationId) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PostBaseMigrationRead[]>(queryKey);
      queryClient.setQueryData<PostBaseMigrationRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === migrationId ? { ...item, status: 'pending' } : item)),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (result) => {
      queryClient.setQueryData<PostBaseMigrationRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === result.migration.id ? result.migration : item)),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
    },
  });
}

export function usePostBaseBindingSwitchovers(bindingId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));

  return useQuery({
    queryKey: ['postbase', tenantId, 'bindings', bindingId, 'switchovers'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseSwitchoverRead[]>(`/bindings/${bindingId}/switchovers`);
      return response.data;
    },
    enabled: Boolean(bindingId),
    staleTime: 10_000,
  });
}

export function useExecutePostBaseSwitchover(bindingId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'bindings', bindingId, 'switchovers'] as const;

  return useMutation({
    mutationFn: async (switchoverId: string) => {
      const response = await apiClient.post<PostBaseSwitchoverRead>(`/switchovers/${switchoverId}/execute`);
      return response.data;
    },
    onMutate: async (switchoverId) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PostBaseSwitchoverRead[]>(queryKey);
      queryClient.setQueryData<PostBaseSwitchoverRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === switchoverId ? { ...item, status: 'running' } : item)),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (switchover) => {
      queryClient.setQueryData<PostBaseSwitchoverRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === switchover.id ? switchover : item)),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'projects'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', undefined, 'bindings'] });
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
      queryClient.setQueryData<PostBaseSecretRead[]>(['postbase', tenantId, 'environments', environmentId, 'secrets'], (current = []) => [
        secret,
        ...current,
      ]);
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'projects'] });
    },
  });
}

export function useRotatePostBaseSecret(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'secrets'] as const;

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
      const previous = queryClient.getQueryData<PostBaseSecretRead[]>(queryKey);
      queryClient.setQueryData<PostBaseSecretRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === secretId ? { ...item, status: 'rotating' } : item)),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (result) => {
      queryClient.setQueryData<PostBaseSecretRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === result.secret.id ? result.secret : item)),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
    },
  });
}

export function useDeactivatePostBaseSecret(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'secrets'] as const;

  return useMutation({
    mutationFn: async (secretId: string) => {
      await apiClient.delete(`/environments/${environmentId}/secrets/${secretId}`);
      return secretId;
    },
    onMutate: async (secretId) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PostBaseSecretRead[]>(queryKey);
      queryClient.setQueryData<PostBaseSecretRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === secretId ? { ...item, status: 'revoked' } : item)),
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
      queryClient.setQueryData<PostBaseBindingRead[]>(['postbase', tenantId, 'environments', environmentId, 'bindings'], (current = []) => [
        binding,
        ...current,
      ]);
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'projects'] });
    },
  });
}

export function useUpdatePostBaseBindingStatus(environmentId: string | undefined) {
  const tenantId = useAuthStore((state) => resolvePostBaseContextKey(state.tenant?.id));
  const queryClient = useQueryClient();
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'bindings'] as const;

  return useMutation({
    mutationFn: async ({ bindingId, payload }: { bindingId: string; payload: PostBaseBindingStatusPayload }) => {
      const response = await apiClient.post<PostBaseBindingRead>(`/bindings/${bindingId}/status`, payload);
      return response.data;
    },
    onMutate: async ({ bindingId, payload }) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PostBaseBindingRead[]>(queryKey);
      queryClient.setQueryData<PostBaseBindingRead[]>(queryKey, (current = []) =>
        current.map((item) =>
          item.id === bindingId ? { ...item, status: payload.status, last_transition_reason: payload.reason ?? 'manual_status_update' } : item,
        ),
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: async (binding) => {
      queryClient.setQueryData<PostBaseBindingRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === binding.id ? binding : item)),
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
      queryClient.setQueryData<PostBaseSwitchoverRead[]>(['postbase', tenantId, 'bindings', bindingId, 'switchovers'], (current = []) => [
        switchover,
        ...current,
      ]);
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
  const queryKey = ['postbase', tenantId, 'environments', environmentId, 'migrations'] as const;

  return useMutation({
    mutationFn: async (migrationId: string) => {
      const response = await apiClient.post<PostBaseMigrationRead>(
        `/environments/${environmentId}/migrations/${migrationId}/reconcile`,
      );
      return response.data;
    },
    onSuccess: async (migration) => {
      queryClient.setQueryData<PostBaseMigrationRead[]>(queryKey, (current = []) =>
        current.map((item) => (item.id === migration.id ? migration : item)),
      );
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId, 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', tenantId] });
    },
  });
}
