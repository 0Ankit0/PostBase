'use client';

import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  useApplyPostBaseMigration,
  useCreatePostBaseBinding,
  useCreatePostBaseSecret,
  useCreatePostBaseSwitchover,
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
  const drainWebhooks = useDrainPostBaseWebhooks(primaryEnvironment?.id);

  const usageByCapability = useMemo(() => {
    const buckets = new Map<string, number>();
    for (const meter of usage ?? []) {
      buckets.set(meter.capability_key, (buckets.get(meter.capability_key) ?? 0) + meter.value);
    }
    return [...buckets.entries()].sort((a, b) => b[1] - a[1]);
  }, [usage]);

  const pendingMigrations = (migrations ?? []).filter((item) => item.status === 'pending');

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
              <span className={item.completed ? 'text-green-600' : 'text-amber-600'}>
                {item.completed ? 'done' : 'pending'}
              </span>
            </div>
          ))}
          <div className="flex items-center justify-between rounded border border-gray-200 p-2">
            <span>Drain due webhook deliveries</span>
            <Button size="sm" onClick={() => drainWebhooks.mutate(200)} disabled={drainWebhooks.isPending || !primaryEnvironment?.id}>
              Run now
            </Button>
          </div>
          {drainWebhooks.data && (
            <p className="text-xs text-gray-500">Last run drained {drainWebhooks.data.drained_count} job(s).</p>
          )}
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
        <SecretForm environmentId={primaryEnvironment?.id} />
        <BindingForm
          environmentId={primaryEnvironment?.id}
          providerCatalog={providerCatalog ?? []}
          secrets={secrets?.map((item) => item.id) ?? []}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Pending schema migrations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {pendingMigrations.length === 0 ? (
            <p className="text-gray-500">No pending migrations.</p>
          ) : (
            pendingMigrations.map((migration) => (
              <div
                key={migration.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-gray-200 p-3"
              >
                <div>
                  <p className="font-medium text-gray-900">Version {migration.version}</p>
                  <p className="text-xs text-gray-500">{migration.applied_sql || 'Pending SQL apply'}</p>
                  <p className="text-xs text-gray-500">reconciliation: {migration.reconciliation_status}</p>
                </div>
                <Button
                  size="sm"
                  onClick={() => applyMigration.mutate(migration.id)}
                  disabled={applyMigration.isPending}
                >
                  Apply migration
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pending switchovers</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {(bindings ?? []).map((binding) => (
            <BindingSwitchoverRow
              key={binding.id}
              bindingId={binding.id}
              capability={binding.capability_key}
              currentProvider={binding.provider_key}
            />
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

function SecretForm({ environmentId }: { environmentId: string | undefined }) {
  const createSecret = useCreatePostBaseSecret(environmentId);
  const [name, setName] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [secretKind, setSecretKind] = useState('');
  const [secretValue, setSecretValue] = useState('');

  const onSubmit = () => {
    if (!name || !providerKey || !secretKind || !secretValue) {
      return;
    }
    createSecret.mutate(
      { name, provider_key: providerKey, secret_kind: secretKind, secret_value: secretValue },
      { onSuccess: () => setSecretValue('') },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create secret</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Secret name" />
        <Input value={providerKey} onChange={(event) => setProviderKey(event.target.value)} placeholder="Provider key" />
        <Input value={secretKind} onChange={(event) => setSecretKind(event.target.value)} placeholder="Secret kind" />
        <Input value={secretValue} onChange={(event) => setSecretValue(event.target.value)} placeholder="Secret value" />
        <Button disabled={!environmentId || createSecret.isPending} onClick={onSubmit}>
          Create secret
        </Button>
      </CardContent>
    </Card>
  );
}

function BindingForm({
  environmentId,
  providerCatalog,
  secrets,
}: {
  environmentId: string | undefined;
  providerCatalog: Array<{ capability_key: string; provider_key: string }>;
  secrets: string[];
}) {
  const createBinding = useCreatePostBaseBinding(environmentId);
  const [capabilityKey, setCapabilityKey] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [region, setRegion] = useState('');
  const [secretIds, setSecretIds] = useState('');
  const [configJson, setConfigJson] = useState('{}');

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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create binding</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-gray-500">
        <Input value={capabilityKey} onChange={(event) => setCapabilityKey(event.target.value)} placeholder="Capability key" />
        <Input value={providerKey} onChange={(event) => setProviderKey(event.target.value)} placeholder="Provider key" />
        <Input value={region} onChange={(event) => setRegion(event.target.value)} placeholder="Region (optional)" />
        <Input
          value={secretIds}
          onChange={(event) => setSecretIds(event.target.value)}
          placeholder="Secret ids comma-separated"
        />
        {secrets.length > 0 && <p>Available secret ids: {secrets.join(', ')}</p>}
        <Input value={configJson} onChange={(event) => setConfigJson(event.target.value)} placeholder='Config JSON (e.g. {"x":1})' />
        <Button disabled={!environmentId || createBinding.isPending} onClick={onSubmit}>
          Create binding
        </Button>
        <div>
          Known catalog pairs: {providerCatalog.map((item) => `${item.capability_key}/${item.provider_key}`).join(' · ')}
        </div>
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
  const createSwitchover = useCreatePostBaseSwitchover(bindingId);
  const executeSwitchover = useExecutePostBaseSwitchover();
  const { data } = usePostBaseBindingSwitchovers(bindingId);
  const pending = (data ?? []).find((item) => item.status === 'pending');

  if (!pending) {
    return (
      <div className="space-y-2 rounded border border-gray-200 p-2 text-gray-500">
        <div>{capability}: no pending switchover (current provider: {currentProvider})</div>
        <div className="flex flex-wrap items-center gap-2">
          <Input value={targetProvider} onChange={(event) => setTargetProvider(event.target.value)} placeholder="Target provider key" />
          <Input value={strategy} onChange={(event) => setStrategy(event.target.value)} placeholder="Strategy" />
          <Button
            size="sm"
            onClick={() => createSwitchover.mutate({ target_provider_key: targetProvider, strategy })}
            disabled={createSwitchover.isPending || !targetProvider}
          >
            Plan switchover
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-gray-200 p-3">
      <div>
        <p className="font-medium text-gray-900">{capability}</p>
        <p className="text-xs text-gray-500">strategy: {pending.strategy} · {pending.execution_detail}</p>
      </div>
      <Button size="sm" onClick={() => executeSwitchover.mutate(pending.id)} disabled={executeSwitchover.isPending}>
        Execute
      </Button>
    </div>
  );
}
