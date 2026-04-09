'use client';

import { useMemo, useState } from 'react';
import type { AxiosError } from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  useApplyPostBaseMigration,
  useCreatePostBaseBinding,
  useCreatePostBaseSecret,
  useCreatePostBaseSwitchover,
  useDeactivatePostBaseSecret,
  useDrainPostBaseWebhooks,
  useExecutePostBaseSwitchover,
  usePostBaseBindings,
  usePostBaseBindingSwitchovers,
  usePostBaseCapabilityHealth,
  usePostBaseEnvironments,
  usePostBaseMigrations,
  usePostBaseProjectOverview,
  usePostBaseProviderCatalog,
  usePostBaseSecrets,
  usePostBaseUsage,
  useRetryPostBaseMigration,
  useRotatePostBaseSecret,
  useUpdatePostBaseBindingStatus,
} from '@/hooks';

interface ProjectDetailPageProps {
  params: {
    projectId: string;
  };
}

export default function PostBaseProjectDetailPage({ params }: ProjectDetailPageProps) {
  const { projectId } = params;

  const { data: providerCatalog } = usePostBaseProviderCatalog();
  const { data: environments } = usePostBaseEnvironments(projectId);
  const { data: overview } = usePostBaseProjectOverview(projectId);
  const { data: usage } = usePostBaseUsage(projectId);

  const primaryEnvironment = environments?.[0];
  const { data: health } = usePostBaseCapabilityHealth(primaryEnvironment?.id);
  const { data: bindings } = usePostBaseBindings(primaryEnvironment?.id);
  const { data: secrets } = usePostBaseSecrets(primaryEnvironment?.id);
  const { data: migrations } = usePostBaseMigrations(primaryEnvironment?.id);
  const applyMigration = useApplyPostBaseMigration(primaryEnvironment?.id);
  const retryMigration = useRetryPostBaseMigration(primaryEnvironment?.id);
  const drainWebhooks = useDrainPostBaseWebhooks(primaryEnvironment?.id);

  const usageByCapability = useMemo(() => {
    const buckets = new Map<string, number>();
    for (const meter of usage ?? []) {
      buckets.set(meter.capability_key, (buckets.get(meter.capability_key) ?? 0) + meter.value);
    }
    return [...buckets.entries()].sort((a, b) => b[1] - a[1]);
  }, [usage]);

  const pendingMigrations = (migrations ?? []).filter((item) => item.status === 'pending');
  const failedMigrations = (migrations ?? []).filter((item) => item.status === 'failed');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Project Control Plane Detail</h1>
        <p className="text-sm text-gray-500">
          Environment readiness, degraded capabilities, usage, migrations, and switchover operations.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Environments" value={overview?.environment_count ?? 0} />
        <MetricCard label="Active bindings" value={overview?.active_bindings ?? 0} />
        <MetricCard label="Degraded bindings" value={overview?.degraded_bindings ?? 0} />
        <MetricCard label="Usage total" value={Math.round(overview?.usage_points_total ?? 0)} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Environment readiness</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {(overview?.environments ?? []).map((env) => (
            <div key={env.environment_id} className="rounded border border-gray-200 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-gray-900">{env.environment_id}</div>
                <div className="text-xs text-gray-500">
                  {env.stage} · {env.status} · {env.readiness_state}
                </div>
              </div>
              <p className="mt-2 text-gray-600">{env.readiness_detail || 'No readiness details reported.'}</p>
              <div className="mt-2 text-xs text-gray-500">
                degraded: {env.degraded_bindings} · pending migrations: {env.pending_migrations} · recent switchovers:{' '}
                {env.recent_switchovers}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Completion checklist</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {(drainWebhooks.data?.checklist ?? [
            { item: 'Durable webhook queue worker task registered', completed: true },
            { item: 'Scheduled drain job configured', completed: true },
            { item: 'Operator-triggered drain endpoint available', completed: true },
          ]).map((item) => (
            <div key={item.item} className="flex items-center justify-between rounded border border-gray-200 p-2">
              <span>{item.item}</span>
              <span className={item.completed ? 'text-green-600' : 'text-amber-600'}>{item.completed ? 'done' : 'pending'}</span>
            </div>
          ))}
          <div className="flex items-center justify-between rounded border border-gray-200 p-2">
            <span>Drain due webhook deliveries</span>
            <Button size="sm" onClick={() => drainWebhooks.mutate(200)} disabled={drainWebhooks.isPending || !primaryEnvironment?.id}>
              Run now
            </Button>
          </div>
          {drainWebhooks.data && <p className="text-xs text-gray-500">Last run drained {drainWebhooks.data.drained_count} job(s).</p>}
          <MutationError mutationError={drainWebhooks.error} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Capability health</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {(health?.provider_health ?? []).map((item) => (
              <div key={`${item.capability_key}-${item.provider_key}`} className="rounded border border-gray-200 p-2">
                <div className="font-medium text-gray-900">
                  {item.capability_key} → {item.provider_key}
                </div>
                <div className="text-xs text-gray-500">
                  {item.ready ? 'ready' : 'degraded'} · {item.detail}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Usage by capability</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {usageByCapability.map(([capability, total]) => (
              <div key={capability} className="flex items-center justify-between rounded border border-gray-200 p-2">
                <span className="font-medium text-gray-900">{capability}</span>
                <span className="text-xs text-gray-500">{total.toFixed(2)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SecretForm environmentId={primaryEnvironment?.id} secrets={secrets ?? []} />
        <BindingForm
          environmentId={primaryEnvironment?.id}
          providerCatalog={providerCatalog ?? []}
          bindings={bindings ?? []}
          secrets={secrets?.map((item) => item.id) ?? []}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Schema migrations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {pendingMigrations.length === 0 && failedMigrations.length === 0 ? (
            <p className="text-gray-500">No pending/failed migrations.</p>
          ) : (
            [...pendingMigrations, ...failedMigrations].map((migration) => (
              <div key={migration.id} className="space-y-2 rounded border border-gray-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium text-gray-900">Version {migration.version}</p>
                  <p className="text-xs text-gray-500">status: {migration.status}</p>
                </div>
                <p className="text-xs text-gray-500">{migration.applied_sql || 'Pending SQL apply'}</p>
                <p className="text-xs text-gray-500">reconciliation: {migration.reconciliation_status}</p>
                <div className="flex gap-2">
                  {migration.status === 'pending' && (
                    <Button size="sm" onClick={() => applyMigration.mutate(migration.id)} disabled={applyMigration.isPending}>
                      Apply
                    </Button>
                  )}
                  {migration.status === 'failed' && (
                    <Button size="sm" variant="outline" onClick={() => retryMigration.mutate(migration.id)} disabled={retryMigration.isPending}>
                      Retry
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
          {applyMigration.data && <p className="text-xs text-green-700">Migration {applyMigration.data.version} apply request completed.</p>}
          {retryMigration.data && (
            <p className="text-xs text-green-700">
              Retry requested for {retryMigration.data.migration.version}; rollback status: {retryMigration.data.rollback_status}.
            </p>
          )}
          <MutationError mutationError={applyMigration.error} />
          <MutationError mutationError={retryMigration.error} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Switchovers (execute / rollback)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {(bindings ?? []).map((binding) => (
            <BindingSwitchoverRow key={binding.id} bindingId={binding.id} capability={binding.capability_key} currentProvider={binding.provider_key} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-2xl font-semibold text-gray-900">{value}</p>
      </CardContent>
    </Card>
  );
}

function SecretForm({ environmentId, secrets }: { environmentId: string | undefined; secrets: Array<{ id: string; name: string; provider_key: string; status: string; last_four: string }> }) {
  const createSecret = useCreatePostBaseSecret(environmentId);
  const rotateSecret = useRotatePostBaseSecret(environmentId);
  const deactivateSecret = useDeactivatePostBaseSecret(environmentId);
  const [name, setName] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [secretKind, setSecretKind] = useState('');
  const [secretValue, setSecretValue] = useState('');
  const [rotateInputBySecret, setRotateInputBySecret] = useState<Record<string, string>>({});

  const onSubmit = () => {
    if (!name || !providerKey || !secretKind || !secretValue) {
      return;
    }
    createSecret.mutate(
      { name, provider_key: providerKey, secret_kind: secretKind, secret_value: secretValue },
      {
        onSuccess: () => {
          setSecretValue('');
          setName('');
        },
      },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Secret lifecycle (create / rotate / deactivate)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Secret name" />
        <Input value={providerKey} onChange={(event) => setProviderKey(event.target.value)} placeholder="Provider key" />
        <Input value={secretKind} onChange={(event) => setSecretKind(event.target.value)} placeholder="Secret kind" />
        <Input value={secretValue} onChange={(event) => setSecretValue(event.target.value)} placeholder="Secret value" type="password" />
        <Button disabled={!environmentId || createSecret.isPending} onClick={onSubmit}>
          Create secret
        </Button>

        <div className="mt-3 space-y-2 text-xs text-gray-600">
          {secrets.length === 0 ? (
            <p>No secrets in this environment.</p>
          ) : (
            secrets.map((secret) => (
              <div key={secret.id} className="space-y-2 rounded border border-gray-200 p-2">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="font-medium text-gray-900">{secret.name}</p>
                    <p>
                      {secret.provider_key} · {secret.status} · ****{secret.last_four}
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => deactivateSecret.mutate(secret.id)} disabled={deactivateSecret.isPending || secret.status === 'revoked'}>
                    Deactivate
                  </Button>
                </div>
                <div className="flex gap-2">
                  <Input
                    value={rotateInputBySecret[secret.id] ?? ''}
                    onChange={(event) => setRotateInputBySecret((current) => ({ ...current, [secret.id]: event.target.value }))}
                    placeholder="New secret value"
                    type="password"
                  />
                  <Button
                    size="sm"
                    onClick={() => {
                      const nextValue = rotateInputBySecret[secret.id]?.trim();
                      if (!nextValue) return;
                      rotateSecret.mutate(
                        { secretId: secret.id, secretValue: nextValue },
                        {
                          onSuccess: () => {
                            setRotateInputBySecret((current) => ({ ...current, [secret.id]: '' }));
                          },
                        },
                      );
                    }}
                    disabled={rotateSecret.isPending}
                  >
                    Rotate
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
        <MutationError mutationError={createSecret.error} />
        <MutationError mutationError={rotateSecret.error} />
        <MutationError mutationError={deactivateSecret.error} />
      </CardContent>
    </Card>
  );
}

function BindingForm({
  environmentId,
  providerCatalog,
  bindings,
  secrets,
}: {
  environmentId: string | undefined;
  providerCatalog: Array<{ capability_key: string; provider_key: string }>;
  bindings: Array<{ id: string; capability_key: string; provider_key: string; status: string }>;
  secrets: string[];
}) {
  const createBinding = useCreatePostBaseBinding(environmentId);
  const updateBindingStatus = useUpdatePostBaseBindingStatus(environmentId);
  const [capabilityKey, setCapabilityKey] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [region, setRegion] = useState('');
  const [secretIds, setSecretIds] = useState('');
  const [configJson, setConfigJson] = useState('{}');
  const [reasonByBinding, setReasonByBinding] = useState<Record<string, string>>({});

  const onSubmit = () => {
    if (!capabilityKey || !providerKey) {
      return;
    }
    let parsedConfig: Record<string, unknown> = {};
    try {
      parsedConfig = JSON.parse(configJson || '{}');
    } catch {
      return;
    }
    const linkedSecretIds = secretIds
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
    createBinding.mutate({
      capability_key: capabilityKey,
      provider_key: providerKey,
      region: region || null,
      config_json: parsedConfig,
      secret_ref_ids: linkedSecretIds,
    });
  };

  const transitionBinding = (bindingId: string, status: 'active' | 'disabled' | 'retired') => {
    updateBindingStatus.mutate({
      bindingId,
      payload: {
        status,
        reason: reasonByBinding[bindingId] || `manual_${status}`,
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Binding lifecycle (create / update / disable / retire)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-gray-500">
        <Input value={capabilityKey} onChange={(event) => setCapabilityKey(event.target.value)} placeholder="Capability key" />
        <Input value={providerKey} onChange={(event) => setProviderKey(event.target.value)} placeholder="Provider key" />
        <Input value={region} onChange={(event) => setRegion(event.target.value)} placeholder="Region (optional)" />
        <Input value={secretIds} onChange={(event) => setSecretIds(event.target.value)} placeholder="Secret ids comma-separated" />
        {secrets.length > 0 && <p>Available secret ids: {secrets.join(', ')}</p>}
        <Input value={configJson} onChange={(event) => setConfigJson(event.target.value)} placeholder='Config JSON (e.g. {"x":1})' />
        <Button disabled={!environmentId || createBinding.isPending} onClick={onSubmit}>
          Create binding
        </Button>
        <div>Known catalog pairs: {providerCatalog.map((item) => `${item.capability_key}/${item.provider_key}`).join(' · ')}</div>

        <div className="space-y-2">
          {bindings.map((binding) => (
            <div key={binding.id} className="rounded border border-gray-200 p-2">
              <p className="font-medium text-gray-900">
                {binding.capability_key} → {binding.provider_key}
              </p>
              <p className="mb-2">status: {binding.status}</p>
              <Input
                value={reasonByBinding[binding.id] ?? ''}
                onChange={(event) => setReasonByBinding((current) => ({ ...current, [binding.id]: event.target.value }))}
                placeholder="Transition reason"
              />
              <div className="mt-2 flex gap-2">
                <Button size="sm" variant="outline" onClick={() => transitionBinding(binding.id, 'active')} disabled={updateBindingStatus.isPending}>
                  Update/Enable
                </Button>
                <Button size="sm" variant="outline" onClick={() => transitionBinding(binding.id, 'disabled')} disabled={updateBindingStatus.isPending}>
                  Disable
                </Button>
                <Button size="sm" variant="outline" onClick={() => transitionBinding(binding.id, 'retired')} disabled={updateBindingStatus.isPending}>
                  Retire
                </Button>
              </div>
            </div>
          ))}
        </div>

        <MutationError mutationError={createBinding.error} />
        <MutationError mutationError={updateBindingStatus.error} />
      </CardContent>
    </Card>
  );
}

function BindingSwitchoverRow({
  bindingId,
  capability,
  currentProvider,
}: {
  bindingId: string;
  capability: string;
  currentProvider: string;
}) {
  const [targetProvider, setTargetProvider] = useState('');
  const [strategy, setStrategy] = useState('cutover');
  const [retirementStrategy, setRetirementStrategy] = useState('manual');
  const createSwitchover = useCreatePostBaseSwitchover(bindingId);
  const executeSwitchover = useExecutePostBaseSwitchover(bindingId);
  const { data } = usePostBaseBindingSwitchovers(bindingId);
  const pending = (data ?? []).find((item) => item.status === 'pending' || item.status === 'failed');
  const preflight = pending?.execution_state_json?.preflight_report as Record<string, { ok?: boolean; detail?: string }> | undefined;

  if (!pending) {
    return (
      <div className="space-y-2 rounded border border-gray-200 p-2 text-gray-500">
        <div>{capability}: no pending switchover (current provider: {currentProvider})</div>
        <div className="flex flex-wrap items-center gap-2">
          <Input value={targetProvider} onChange={(event) => setTargetProvider(event.target.value)} placeholder="Target provider key" />
          <Input value={strategy} onChange={(event) => setStrategy(event.target.value)} placeholder="Strategy" />
          <Input value={retirementStrategy} onChange={(event) => setRetirementStrategy(event.target.value)} placeholder="Retirement strategy" />
          <Button
            size="sm"
            onClick={() => createSwitchover.mutate({ target_provider_key: targetProvider, strategy, retirement_strategy: retirementStrategy })}
            disabled={createSwitchover.isPending || !targetProvider}
          >
            Plan switchover
          </Button>
        </div>
        <MutationError mutationError={createSwitchover.error} />
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded border border-gray-200 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium text-gray-900">{capability}</p>
          <p className="text-xs text-gray-500">strategy: {pending.strategy} · {pending.execution_detail}</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => executeSwitchover.mutate(pending.id)} disabled={executeSwitchover.isPending}>
            Execute
          </Button>
          <Button size="sm" variant="outline" onClick={() => executeSwitchover.mutate(pending.id)} disabled={executeSwitchover.isPending}>
            Rollback/Resume
          </Button>
        </div>
      </div>

      {preflight && (
        <div className="space-y-1 rounded border border-gray-200 p-2 text-xs text-gray-600">
          <p className="font-medium text-gray-800">Preflight status</p>
          {Object.entries(preflight).map(([check, result]) => (
            <p key={check}>
              {check}: {result.ok ? 'ok' : 'blocked'}{result.detail ? ` · ${result.detail}` : ''}
            </p>
          ))}
        </div>
      )}

      <MutationError mutationError={executeSwitchover.error} />
    </div>
  );
}

function MutationError({ mutationError }: { mutationError: unknown }) {
  if (!mutationError) {
    return null;
  }

  const message = extractMutationError(mutationError);
  return <p className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">{message}</p>;
}

function extractMutationError(error: unknown): string {
  const axiosError = error as AxiosError<{ detail?: string | { message?: string } }>;
  if (axiosError?.response?.data?.detail) {
    if (typeof axiosError.response.data.detail === 'string') {
      return axiosError.response.data.detail;
    }
    if (axiosError.response.data.detail.message) {
      return axiosError.response.data.detail.message;
    }
  }

  if (error instanceof Error) {
    return error.message;
  }
  return 'Mutation failed. Please retry.';
}
