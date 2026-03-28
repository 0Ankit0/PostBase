'use client';

import { useQuery } from '@tanstack/react-query';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type {
  PaginatedResponse,
  PostBaseBindingRead,
  PostBaseCapabilityHealthReport,
  PostBaseEnvironmentRead,
  PostBaseProjectOverview,
  PostBaseProjectRead,
  PostBaseProviderCatalogRead,
  PostBaseSecretRead,
  PostBaseMigrationRead,
  PostBaseSwitchoverRead,
  PostBaseUsageMeterRead,
  PostBaseWebhookDrainResult,
} from '@/types';

export function usePostBaseProviderCatalog() {
  return useQuery({
    queryKey: ['postbase', 'provider-catalog'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseProviderCatalogRead[]>('/provider-catalog');
      return response.data;
    },
    staleTime: 60_000,
  });
}

export function usePostBaseProjects() {
  return useQuery({
    queryKey: ['postbase', 'projects'],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedResponse<PostBaseProjectRead>>('/projects');
      return response.data;
    },
    staleTime: 30_000,
  });
}

export function usePostBaseEnvironments(projectId: string | undefined) {
  return useQuery({
    queryKey: ['postbase', 'projects', projectId, 'environments'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseEnvironmentRead[]>(`/projects/${projectId}/environments`);
      return response.data;
    },
    enabled: Boolean(projectId),
    staleTime: 30_000,
  });
}

export function usePostBaseBindings(environmentId: string | undefined) {
  return useQuery({
    queryKey: ['postbase', 'environments', environmentId, 'bindings'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseBindingRead[]>(`/environments/${environmentId}/bindings`);
      return response.data;
    },
    enabled: Boolean(environmentId),
    staleTime: 15_000,
  });
}

export function usePostBaseSecrets(environmentId: string | undefined) {
  return useQuery({
    queryKey: ['postbase', 'environments', environmentId, 'secrets'],
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

export interface PostBaseSwitchoverCreatePayload {
  target_provider_key: string;
  strategy?: string;
}

export function usePostBaseProjectOverview(projectId: string | undefined) {
  return useQuery({
    queryKey: ['postbase', 'projects', projectId, 'overview'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseProjectOverview>(`/projects/${projectId}/overview`);
      return response.data;
    },
    enabled: Boolean(projectId),
    staleTime: 15_000,
  });
}

export function usePostBaseUsage(projectId: string | undefined) {
  return useQuery({
    queryKey: ['postbase', 'projects', projectId, 'usage'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseUsageMeterRead[]>(`/projects/${projectId}/usage`);
      return response.data;
    },
    enabled: Boolean(projectId),
    staleTime: 15_000,
  });
}

export function usePostBaseCapabilityHealth(environmentId: string | undefined) {
  return useQuery({
    queryKey: ['postbase', 'environments', environmentId, 'health'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseCapabilityHealthReport>(
        `/environments/${environmentId}/reports/capability-health`,
      );
      return response.data;
    },
    enabled: Boolean(environmentId),
    staleTime: 15_000,
  });
}

export function usePostBaseMigrations(environmentId: string | undefined) {
  return useQuery({
    queryKey: ['postbase', 'environments', environmentId, 'migrations'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseMigrationRead[]>(
        `/environments/${environmentId}/migrations`,
      );
      return response.data;
    },
    enabled: Boolean(environmentId),
    staleTime: 10_000,
  });
}

export function useApplyPostBaseMigration(environmentId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (migrationId: string) => {
      const response = await apiClient.post<PostBaseMigrationRead>(
        `/environments/${environmentId}/migrations/${migrationId}/apply`,
      );
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['postbase', 'environments', environmentId, 'migrations'],
      });
      await queryClient.invalidateQueries({
        queryKey: ['postbase', 'environments', environmentId, 'health'],
      });
    },
  });
}

export function usePostBaseBindingSwitchovers(bindingId: string | undefined) {
  return useQuery({
    queryKey: ['postbase', 'bindings', bindingId, 'switchovers'],
    queryFn: async () => {
      const response = await apiClient.get<PostBaseSwitchoverRead[]>(
        `/bindings/${bindingId}/switchovers`,
      );
      return response.data;
    },
    enabled: Boolean(bindingId),
    staleTime: 10_000,
  });
}

export function useExecutePostBaseSwitchover() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (switchoverId: string) => {
      const response = await apiClient.post<PostBaseSwitchoverRead>(
        `/switchovers/${switchoverId}/execute`,
      );
      return response.data;
    },
    onSuccess: async (_, switchoverId) => {
      await queryClient.invalidateQueries({
        queryKey: ['postbase', 'switchovers', switchoverId],
      });
      await queryClient.invalidateQueries({
        queryKey: ['postbase'],
      });
    },
  });
}


export function useCreatePostBaseSecret(environmentId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PostBaseSecretCreatePayload) => {
      const response = await apiClient.post<PostBaseSecretRead>(`/environments/${environmentId}/secrets`, payload);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'environments', environmentId, 'secrets'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'projects'] });
    },
  });
}

export function useCreatePostBaseBinding(environmentId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PostBaseBindingCreatePayload) => {
      const response = await apiClient.post<PostBaseBindingRead>(`/environments/${environmentId}/bindings`, payload);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'environments', environmentId, 'bindings'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'projects'] });
    },
  });
}

export function useCreatePostBaseSwitchover(bindingId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PostBaseSwitchoverCreatePayload) => {
      const response = await apiClient.post<PostBaseSwitchoverRead>(`/bindings/${bindingId}/switchovers`, payload);
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'bindings', bindingId, 'switchovers'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase'] });
    },
  });
}


export function useDrainPostBaseWebhooks(environmentId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (limit: number = 200) => {
      const response = await apiClient.post<PostBaseWebhookDrainResult>(
        `/environments/${environmentId}/operations/webhooks/drain?limit=${limit}`
      );
      return response.data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'environments', environmentId, 'health'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase', 'environments', environmentId, 'migrations'] });
      await queryClient.invalidateQueries({ queryKey: ['postbase'] });
    },
  });
}
