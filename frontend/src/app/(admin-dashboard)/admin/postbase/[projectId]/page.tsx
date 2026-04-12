'use client';

import { useEffect, useMemo, useState } from 'react';
import type { AxiosError } from 'axios';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
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
  useReconcilePostBaseMigration,
  useRecoverPostBaseWebhooks,
  usePostBaseSecrets,
  usePostBaseUsage,
  useRetryPostBaseMigration,
  useRotatePostBaseSecret,
  useUpdatePostBaseBindingStatus,
} from '@/hooks';
import type { PostBaseEnvironmentRead } from '@/types';

interface ProjectDetailPageProps {
  params: {
    projectId: string;
  };
}

export default function PostBaseProjectDetailPage({ params }: ProjectDetailPageProps) {
  const { projectId } = params;
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const { data: providerCatalog } = usePostBaseProviderCatalog();
  const environmentsQuery = usePostBaseEnvironments(projectId);
  const overviewQuery = usePostBaseProjectOverview(projectId);
  const { data: environments } = environmentsQuery;
  const { data: overview } = overviewQuery;
  const { data: usage } = usePostBaseUsage(projectId);

  const environmentItems = environments?.items ?? [];
  const initialSelectedEnvironment = useMemo(
    () => resolveSelectedEnvironmentId(environmentItems, searchParams.get('env')),
    [environmentItems, searchParams],
  );
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(initialSelectedEnvironment);

  useEffect(() => {
    setSelectedEnvironmentId(resolveSelectedEnvironmentId(environmentItems, searchParams.get('env')));
  }, [environmentItems, searchParams]);

  const selectedEnvironment = useMemo(
    () => environmentItems.find((environment) => environment.id === selectedEnvironmentId) ?? environmentItems[0],
    [environmentItems, selectedEnvironmentId],
  );

  const selectedEnvironmentOverview = useMemo(
    () =>
      (overview?.environments ?? []).find((environment) => environment.environment_id === selectedEnvironment?.id) ?? null,
    [overview?.environments, selectedEnvironment?.id],
  );

  const healthQuery = usePostBaseCapabilityHealth(selectedEnvironment?.id);
  const { data: health } = healthQuery;
  const { data: bindings } = usePostBaseBindings(selectedEnvironment?.id);
  const { data: secrets } = usePostBaseSecrets(selectedEnvironment?.id);
  const { data: migrations } = usePostBaseMigrations(selectedEnvironment?.id);
  const applyMigration = useApplyPostBaseMigration(selectedEnvironment?.id);
  const retryMigration = useRetryPostBaseMigration(selectedEnvironment?.id);
  const reconcileMigration = useReconcilePostBaseMigration(selectedEnvironment?.id);
  const drainWebhooks = useDrainPostBaseWebhooks(selectedEnvironment?.id);
  const recoverWebhooks = useRecoverPostBaseWebhooks(selectedEnvironment?.id);
  const [runningActions, setRunningActions] = useState<Record<string, boolean>>({});
  const [latestOperationSummary, setLatestOperationSummary] = useState<string | null>(null);

  const usageItems = usage?.items ?? [];
  const migrationItems = migrations?.items ?? [];
  const bindingItems = bindings?.items ?? [];
  const secretItems = secrets?.items ?? [];

  const usageByCapability = useMemo(() => {
    const buckets = new Map<string, number>();
    for (const meter of usageItems) {
      buckets.set(meter.capability_key, (buckets.get(meter.capability_key) ?? 0) + meter.value);
    }
    return [...buckets.entries()].sort((a, b) => b[1] - a[1]);
  }, [usageItems]);

  const pendingMigrations = migrationItems.filter((item) => item.status === 'pending');
  const failedMigrations = migrationItems.filter((item) => item.status === 'failed');
  const needsReconciliation = migrationItems.filter((item) => item.reconciliation_status !== 'in_sync');
  const isProductionEnvironment = shouldRequireProductionConfirmation(selectedEnvironment?.stage);

  const switchEnvironment = (environmentId: string) => {
    setSelectedEnvironmentId(environmentId);
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set('env', environmentId);
    router.replace(`${pathname}?${nextParams.toString()}`, { scroll: false });
  };

  const runAction = async (actionKey: string, action: () => Promise<void>) => {
    if (runningActions[actionKey]) {
      return;
    }
    setRunningActions((current) => ({ ...current, [actionKey]: true }));
    try {
      await action();
    } finally {
      setRunningActions((current) => ({ ...current, [actionKey]: false }));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Project Control Plane Detail</h1>
        <p className="text-sm text-gray-500">
          Environment readiness, degraded capabilities, usage, migrations, and switchover operations.
        </p>
        <p className="mt-1 text-xs text-gray-500">
          Active environment: <span className="font-medium text-gray-700">{selectedEnvironment?.name ?? 'No environment selected'}</span>
        </p>
      </div>

      <EnvironmentSelector
        environments={environmentItems}
        selectedEnvironmentId={selectedEnvironment?.id}
        selectedOverview={selectedEnvironmentOverview}
        onSelect={switchEnvironment}
      />

      {isProductionEnvironment ? (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          <p className="font-medium">Production environment safeguards enabled.</p>
          <p>High-impact actions require explicit confirmation. Verify maintenance window, rollback plan, and on-call coverage.</p>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Environments" value={overview?.environment_count ?? 0} />
        <MetricCard label="Active bindings" value={overview?.active_bindings ?? 0} />
        <MetricCard label="Degraded bindings" value={overview?.degraded_bindings ?? 0} />
        <MetricCard label="Usage total" value={Math.round(overview?.usage_points_total ?? 0)} />
      </div>

      {(overviewQuery.isPending || environmentsQuery.isPending) && (
        <Card>
          <CardContent className="pt-6 text-sm text-gray-500">Loading project overview and health snapshots…</CardContent>
        </Card>
      )}

      {overviewQuery.isError && !overview && (
        <QueryErrorCard
          title="Unable to load platform overview"
          message={extractMutationError(overviewQuery.error)}
          onRetry={() => void overviewQuery.refetch()}
        />
      )}

      {healthQuery.isError && !health && (
        <QueryErrorCard
          title="Unable to load capability health"
          message={extractMutationError(healthQuery.error)}
          onRetry={() => void healthQuery.refetch()}
        />
      )}

      {(overviewQuery.isRefetchError && overview) || (healthQuery.isRefetchError && health) ? (
        <StaleDataBanner
          label="Showing cached platform snapshot while polling recovers."
          onRetry={() => {
            void overviewQuery.refetch();
            void healthQuery.refetch();
          }}
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Environment readiness</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {(overview?.environments ?? []).map((env) => (
            <div key={env.environment_id} className="rounded border border-gray-200 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-gray-900">{env.environment_id}</div>
                <StatusPill value={env.status} type="status" />
                <StatusPill value={env.readiness_state} type="readiness" />
              </div>
              <p className="mt-2 text-gray-600">{env.readiness_detail || 'No readiness details reported.'}</p>
              {!isReadinessHealthy(env.readiness_state) && (
                <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                  <p className="font-medium">Failure reasons & remediations</p>
                  {buildReadinessRemediations(env.readiness_detail).map((item) => (
                    <p key={`${env.environment_id}-${item.reason}`}>
                      • <span className="font-medium">{item.reason}</span>: {item.remediation}
                    </p>
                  ))}
                </div>
              )}
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
            <Button
              size="sm"
              onClick={() =>
                runAction('drain-webhooks', async () => {
                  if (!confirmProductionOperation(isProductionEnvironment, 'webhook_drain')) return;
                  const result = await drainWebhooks.mutateAsync(200);
                  setLatestOperationSummary(
                    `Webhook drain complete: ${result.drained_count} job(s) drained (${result.reason}).`,
                  );
                })
              }
              disabled={runningActions['drain-webhooks'] || !selectedEnvironment?.id}
            >
              {runningActions['drain-webhooks'] ? 'Running…' : 'Run now'}
            </Button>
          </div>
          <div className="flex items-center justify-between rounded border border-gray-200 p-2">
            <span>Recover exhausted webhook deliveries</span>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                runAction('recover-webhooks', async () => {
                  if (!confirmProductionOperation(isProductionEnvironment, 'webhook_recover')) return;
                  const result = await recoverWebhooks.mutateAsync(200);
                  setLatestOperationSummary(
                    `Webhook recovery complete: ${result.requeued_jobs}/${result.scanned_failed_jobs} exhausted job(s) re-queued, ${result.skipped_jobs} skipped.`,
                  );
                })
              }
              disabled={runningActions['recover-webhooks'] || !selectedEnvironment?.id}
            >
              {runningActions['recover-webhooks'] ? 'Running…' : 'Run now'}
            </Button>
          </div>
          <div className="flex items-center justify-between rounded border border-gray-200 p-2">
            <span>Reconcile drifted/pending migrations</span>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                runAction('reconcile-all', async () => {
                  if (!confirmProductionOperation(isProductionEnvironment, 'migration_reconcile')) return;
                  if (needsReconciliation.length === 0) {
                    setLatestOperationSummary('No migrations currently require reconciliation.');
                    return;
                  }
                  for (const migration of needsReconciliation) {
                    await reconcileMigration.mutateAsync(migration.id);
                  }
                  setLatestOperationSummary(`Reconciliation run complete for ${needsReconciliation.length} migration(s).`);
                })
              }
              disabled={runningActions['reconcile-all'] || !selectedEnvironment?.id || needsReconciliation.length === 0}
            >
              {runningActions['reconcile-all'] ? 'Running…' : 'Run now'}
            </Button>
          </div>
          {drainWebhooks.data && (
            <p className="text-xs text-gray-500">
              Last run drained {drainWebhooks.data.drained_count} job(s), reason: {drainWebhooks.data.reason}.
            </p>
          )}
          {recoverWebhooks.data && (
            <div className="space-y-1 text-xs text-gray-500">
              <p>
                Last recovery re-queued {recoverWebhooks.data.requeued_jobs} job(s) from {recoverWebhooks.data.scanned_failed_jobs}{' '}
                scanned; skipped {recoverWebhooks.data.skipped_jobs}.
              </p>
              <p>Re-queued dead-letter IDs: {recoverWebhooks.data.exhausted_job_ids.join(', ') || 'none'}.</p>
              <p>Skipped dead-letter IDs: {recoverWebhooks.data.skipped_job_ids.join(', ') || 'none'}.</p>
              <p>
                Reasons:{' '}
                {Object.entries(recoverWebhooks.data.reasons)
                  .map(([reason, count]) => `${reason}=${count}`)
                  .join(', ')}
              </p>
            </div>
          )}
          <OperationStatusSummary
            latestOperationSummary={latestOperationSummary}
            drainError={drainWebhooks.error}
            recoverError={recoverWebhooks.error}
            reconcileError={reconcileMigration.error}
            lastPolledAt={migrationItems[0]?.last_reconciled_at ?? null}
          />
          <MutationError mutationError={drainWebhooks.error} />
          <MutationError mutationError={recoverWebhooks.error} />
          <MutationError mutationError={reconcileMigration.error} />
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
                <div className="text-xs text-gray-500">{item.ready ? 'ready' : 'degraded'} · {item.detail || 'Unknown detail'}</div>
              </div>
            ))}
            {(health?.provider_health ?? []).length === 0 && <p className="text-xs text-gray-500">Health state unknown: no provider report available yet.</p>}
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
        <SecretForm environmentId={selectedEnvironment?.id} secrets={secretItems} isProductionEnvironment={isProductionEnvironment} />
        <BindingForm
          environmentId={selectedEnvironment?.id}
          providerCatalog={providerCatalog?.items ?? []}
          bindings={bindingItems}
          secrets={secretItems.map((item) => item.id)}
          isProductionEnvironment={isProductionEnvironment}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Schema migrations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <OperationGuardNotice operation="migration_apply" isProductionEnvironment={isProductionEnvironment} />
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
                {migration.reconcile_error_text && <p className="text-xs text-red-600">reconcile error: {migration.reconcile_error_text}</p>}
                <div className="flex gap-2">
                  {migration.status === 'pending' && (
                    <Button
                      size="sm"
                      onClick={() =>
                        runAction(`migration-apply-${migration.id}`, async () => {
                          if (!confirmProductionOperation(isProductionEnvironment, 'migration_apply')) return;
                          const result = await applyMigration.mutateAsync(migration.id);
                          setLatestOperationSummary(`Migration ${result.version} apply request accepted (${result.status}).`);
                        })
                      }
                      disabled={applyMigration.isPending || runningActions[`migration-apply-${migration.id}`]}
                    >
                      {runningActions[`migration-apply-${migration.id}`] ? 'Applying…' : 'Apply'}
                    </Button>
                  )}
                  {migration.status === 'failed' && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        runAction(`migration-retry-${migration.id}`, async () => {
                          if (!confirmProductionOperation(isProductionEnvironment, 'migration_retry')) return;
                          const result = await retryMigration.mutateAsync(migration.id);
                          setLatestOperationSummary(
                            `Migration ${result.migration.version} retry requested; rollback status: ${result.rollback_status}.`,
                          );
                        })
                      }
                      disabled={retryMigration.isPending || runningActions[`migration-retry-${migration.id}`]}
                    >
                      {runningActions[`migration-retry-${migration.id}`] ? 'Retrying…' : 'Retry'}
                    </Button>
                  )}
                  {migration.reconciliation_status !== 'in_sync' && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        runAction(`reconcile-${migration.id}`, async () => {
                          if (!confirmProductionOperation(isProductionEnvironment, 'migration_reconcile')) return;
                          const result = await reconcileMigration.mutateAsync(migration.id);
                          setLatestOperationSummary(
                            `Migration ${result.version} reconciliation status: ${result.reconciliation_status}.`,
                          );
                        })
                      }
                      disabled={runningActions[`reconcile-${migration.id}`]}
                    >
                      {runningActions[`reconcile-${migration.id}`] ? 'Reconciling…' : 'Reconcile now'}
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
          <MutationError mutationError={applyMigration.error} operation="migration_apply" />
          <MutationError mutationError={retryMigration.error} operation="migration_retry" />
          <MutationError mutationError={reconcileMigration.error} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Switchovers (execute / rollback)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {bindingItems.map((binding) => (
            <BindingSwitchoverRow
              key={binding.id}
              bindingId={binding.id}
              capability={binding.capability_key}
              currentProvider={binding.provider_key}
              isProductionEnvironment={isProductionEnvironment}
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

function QueryErrorCard({ title, message, onRetry }: { title: string; message: string; onRetry: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="rounded border border-red-200 bg-red-50 p-2 text-red-700">{message}</p>
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </CardContent>
    </Card>
  );
}

function StaleDataBanner({ label, onRetry }: { label: string; onRetry: () => void }) {
  return (
    <div className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
      <div className="flex items-center justify-between gap-2">
        <p>{label}</p>
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry now
        </Button>
      </div>
    </div>
  );
}

function EnvironmentSelector({
  environments,
  selectedEnvironmentId,
  selectedOverview,
  onSelect,
}: {
  environments: PostBaseEnvironmentRead[];
  selectedEnvironmentId: string | undefined;
  selectedOverview: { stage: string; status: string; readiness_state: string } | null;
  onSelect: (environmentId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Environment selector</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {environments.length === 0 ? (
          <p className="text-gray-500">No environments are currently available for this project.</p>
        ) : (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {environments.map((environment) => {
              const selected = selectedEnvironmentId === environment.id;
              return (
                <button
                  key={environment.id}
                  type="button"
                  onClick={() => onSelect(environment.id)}
                  className={`rounded border p-3 text-left ${
                    selected ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <p className="font-medium text-gray-900">{environment.name}</p>
                  <p className="text-xs text-gray-500">{environment.id}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <StatusPill value={environment.stage} type="status" />
                    <StatusPill value={environment.status} type="status" />
                    <StatusPill value={environment.readiness_state} type="readiness" />
                  </div>
                </button>
              );
            })}
          </div>
        )}
        {selectedOverview ? (
          <p className="text-xs text-gray-500">
            Active stage/status/readiness: {selectedOverview.stage} · {selectedOverview.status} · {selectedOverview.readiness_state}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function StatusPill({ value, type }: { value: string; type: 'status' | 'readiness' }) {
  const normalized = normalizeStatus(value);
  const tone = getStatusTone(normalized, type);
  return (
    <span className={`rounded px-2 py-0.5 text-xs ${tone}`}>{normalized}</span>
  );
}

function normalizeStatus(value: string | null | undefined): string {
  if (!value || value.trim().length === 0) return 'unknown';
  return value.toLowerCase();
}

function getStatusTone(value: string, type: 'status' | 'readiness'): string {
  if (value === 'degraded' || value === 'not_ready') return 'border border-amber-200 bg-amber-50 text-amber-800';
  if (value === 'ready' || value === 'active') return 'border border-green-200 bg-green-50 text-green-800';
  if (value === 'inactive' || value === 'failed') return 'border border-red-200 bg-red-50 text-red-800';
  return type === 'readiness'
    ? 'border border-slate-200 bg-slate-100 text-slate-700'
    : 'border border-gray-200 bg-gray-100 text-gray-700';
}

interface ReadinessRemediation {
  reason: string;
  remediation: string;
}

export type QuerySurfaceState = 'loading' | 'error' | 'stale-cache' | 'success';

export function deriveQuerySurfaceState({
  isPending,
  isError,
  hasData,
}: {
  isPending: boolean;
  isError: boolean;
  hasData: boolean;
}): QuerySurfaceState {
  if (isPending && !hasData) return 'loading';
  if (isError && hasData) return 'stale-cache';
  if (isError) return 'error';
  return 'success';
}

export function resolveSelectedEnvironmentId(
  environments: PostBaseEnvironmentRead[],
  requestedEnvironmentId: string | null | undefined,
): string | undefined {
  if (requestedEnvironmentId && environments.some((environment) => environment.id === requestedEnvironmentId)) {
    return requestedEnvironmentId;
  }
  return environments[0]?.id;
}

export function shouldRequireProductionConfirmation(stage: PostBaseEnvironmentRead['stage'] | undefined): boolean {
  return stage === 'production';
}

const READINESS_REMEDIATION_RULES: Array<{ keywords: string[]; remediation: ReadinessRemediation }> = [
  {
    keywords: ['secret', 'credential', 'key'],
    remediation: {
      reason: 'Credentials are missing or invalid',
      remediation: 'Rotate or re-create provider secrets, then re-run validation.',
    },
  },
  {
    keywords: ['migration', 'schema', 'drift'],
    remediation: {
      reason: 'Schema migration drift detected',
      remediation: 'Run reconciliation, inspect drift details, and retry failed migrations.',
    },
  },
  {
    keywords: ['degraded', 'provider', 'adapter'],
    remediation: {
      reason: 'Provider capability is degraded',
      remediation: 'Inspect provider health and fail over to a certified adapter if available.',
    },
  },
];

export function isReadinessHealthy(readinessState: string) {
  return readinessState === 'ready';
}

export function buildReadinessRemediations(readinessDetail: string): ReadinessRemediation[] {
  const detail = readinessDetail.toLowerCase();
  const matches = READINESS_REMEDIATION_RULES.filter((rule) => rule.keywords.some((keyword) => detail.includes(keyword))).map(
    (rule) => rule.remediation,
  );

  if (matches.length > 0) {
    return matches;
  }

  return [
    {
      reason: 'Validation checks did not pass',
      remediation: 'Review capability health and execute the suggested run-now operational jobs.',
    },
  ];
}

interface OperationStatusSummaryProps {
  latestOperationSummary: string | null;
  drainError: unknown;
  recoverError: unknown;
  reconcileError: unknown;
  lastPolledAt: string | null;
}

type HighRiskOperation =
  | 'binding_create'
  | 'binding_transition'
  | 'secret_create'
  | 'secret_rotate'
  | 'secret_deactivate'
  | 'webhook_drain'
  | 'webhook_recover'
  | 'migration_apply'
  | 'migration_reconcile'
  | 'migration_retry'
  | 'switchover_plan'
  | 'switchover_execute';

function confirmProductionOperation(isProductionEnvironment: boolean, operation: HighRiskOperation): boolean {
  if (!isProductionEnvironment) return true;
  return window.confirm(
    `Production safeguard: confirm you want to continue with ${operation.replace('_', ' ')}. Ensure rollback and monitoring are ready.`,
  );
}

const HIGH_RISK_PREFLIGHT_COPY: Record<HighRiskOperation, string> = {
  binding_create:
    'Preflight: verify capability/provider pairing, region policy, and linked secret IDs before creating a binding.',
  binding_transition:
    'Preflight: confirm dependent workloads can tolerate this binding state transition and provide an audit reason.',
  secret_create:
    'Preflight: confirm provider identity and scope; incorrect secrets can hard-fail traffic.',
  secret_rotate:
    'Preflight: ensure downstream adapters accept the new credential before rotating.',
  secret_deactivate:
    'Preflight: make sure no active binding still references this secret.',
  webhook_drain:
    'Preflight: verify queue consumers and retry policy; draining can re-order delivery under load.',
  webhook_recover:
    'Preflight: confirm failed job root causes are fixed before re-queueing exhausted deliveries.',
  migration_apply:
    'Preflight: run drift checks and verify no long-running writes are in-flight before applying migration SQL.',
  migration_reconcile:
    'Preflight: inspect drift sources before reconciling to avoid masking the root issue.',
  migration_retry:
    'Preflight: inspect failure and rollback status, then retry only after remediating the root cause.',
  switchover_plan:
    'Preflight: validate target provider readiness and retirement strategy before planning switchover.',
  switchover_execute:
    'Preflight: execute only when all preflight checks are green; blocked checks require remediation first.',
};

export function OperationStatusSummary({
  latestOperationSummary,
  drainError,
  recoverError,
  reconcileError,
  lastPolledAt,
}: OperationStatusSummaryProps) {
  const hasPermissionError = [drainError, recoverError, reconcileError].some((error) => isPermissionDenied(error));
  return (
    <div className="rounded border border-gray-200 bg-gray-50 p-2 text-xs text-gray-600">
      <p className="font-medium text-gray-700">Latest run status</p>
      <p>{latestOperationSummary ?? 'No manual operation run yet in this session.'}</p>
      <p>Outcome summary: {hasPermissionError ? 'Permission-restricted for one or more actions.' : 'No permission blockers reported.'}</p>
      <p>Latest reconciliation poll: {lastPolledAt ? new Date(lastPolledAt).toLocaleString() : 'Awaiting migration poll result.'}</p>
    </div>
  );
}

function SecretForm({
  environmentId,
  secrets,
  isProductionEnvironment,
}: {
  environmentId: string | undefined;
  secrets: Array<{ id: string; name: string; provider_key: string; status: string; last_four: string }>;
  isProductionEnvironment: boolean;
}) {
  const createSecret = useCreatePostBaseSecret(environmentId);
  const rotateSecret = useRotatePostBaseSecret(environmentId);
  const deactivateSecret = useDeactivatePostBaseSecret(environmentId);
  const [name, setName] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [secretKind, setSecretKind] = useState('');
  const [secretValue, setSecretValue] = useState('');
  const [rotateInputBySecret, setRotateInputBySecret] = useState<Record<string, string>>({});
  const [pendingBySecret, setPendingBySecret] = useState<Record<string, boolean>>({});

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
        <OperationGuardNotice operation="secret_create" isProductionEnvironment={isProductionEnvironment} />
        <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Secret name" />
        <Input value={providerKey} onChange={(event) => setProviderKey(event.target.value)} placeholder="Provider key" />
        <Input value={secretKind} onChange={(event) => setSecretKind(event.target.value)} placeholder="Secret kind" />
        <Input value={secretValue} onChange={(event) => setSecretValue(event.target.value)} placeholder="Secret value" type="password" />
        <Button
          disabled={!environmentId || createSecret.isPending}
          onClick={() => {
            if (!confirmProductionOperation(isProductionEnvironment, 'secret_create')) return;
            onSubmit();
          }}
        >
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
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (!confirmProductionOperation(isProductionEnvironment, 'secret_deactivate')) return;
                      if (pendingBySecret[secret.id]) return;
                      setPendingBySecret((current) => ({ ...current, [secret.id]: true }));
                      deactivateSecret.mutate(secret.id, {
                        onSettled: () => setPendingBySecret((current) => ({ ...current, [secret.id]: false })),
                      });
                    }}
                    disabled={deactivateSecret.isPending || pendingBySecret[secret.id] || secret.status === 'revoked'}
                  >
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
                      if (!confirmProductionOperation(isProductionEnvironment, 'secret_rotate')) return;
                      const nextValue = rotateInputBySecret[secret.id]?.trim();
                      if (!nextValue) return;
                      if (pendingBySecret[secret.id]) return;
                      setPendingBySecret((current) => ({ ...current, [secret.id]: true }));
                      rotateSecret.mutate(
                        { secretId: secret.id, secretValue: nextValue },
                        {
                          onSuccess: () => {
                            setRotateInputBySecret((current) => ({ ...current, [secret.id]: '' }));
                          },
                          onSettled: () => {
                            setPendingBySecret((current) => ({ ...current, [secret.id]: false }));
                          },
                        },
                      );
                    }}
                    disabled={rotateSecret.isPending || pendingBySecret[secret.id]}
                  >
                    Rotate
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
        <MutationError mutationError={createSecret.error} operation="secret_create" />
        <MutationError mutationError={rotateSecret.error} operation="secret_rotate" />
        <MutationError mutationError={deactivateSecret.error} operation="secret_deactivate" />
      </CardContent>
    </Card>
  );
}

function BindingForm({
  environmentId,
  providerCatalog,
  bindings,
  secrets,
  isProductionEnvironment,
}: {
  environmentId: string | undefined;
  providerCatalog: Array<{ capability_key: string; provider_key: string }>;
  bindings: Array<{ id: string; capability_key: string; provider_key: string; status: string }>;
  secrets: string[];
  isProductionEnvironment: boolean;
}) {
  const createBinding = useCreatePostBaseBinding(environmentId);
  const updateBindingStatus = useUpdatePostBaseBindingStatus(environmentId);
  const [capabilityKey, setCapabilityKey] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [region, setRegion] = useState('');
  const [secretIds, setSecretIds] = useState('');
  const [configJson, setConfigJson] = useState('{}');
  const [reasonByBinding, setReasonByBinding] = useState<Record<string, string>>({});
  const [transitionPendingByBinding, setTransitionPendingByBinding] = useState<Record<string, boolean>>({});

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
    if (updateBindingStatus.isPending || transitionPendingByBinding[bindingId]) return;
    setTransitionPendingByBinding((current) => ({ ...current, [bindingId]: true }));
    updateBindingStatus.mutate(
      {
        bindingId,
        payload: {
          status,
          reason: reasonByBinding[bindingId] || `manual_${status}`,
        },
      },
      {
        onSettled: () => {
          setTransitionPendingByBinding((current) => ({ ...current, [bindingId]: false }));
        },
      },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Binding lifecycle (create / update / disable / retire)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-gray-500">
        <OperationGuardNotice operation="binding_create" isProductionEnvironment={isProductionEnvironment} />
        <Input value={capabilityKey} onChange={(event) => setCapabilityKey(event.target.value)} placeholder="Capability key" />
        <Input value={providerKey} onChange={(event) => setProviderKey(event.target.value)} placeholder="Provider key" />
        <Input value={region} onChange={(event) => setRegion(event.target.value)} placeholder="Region (optional)" />
        <Input value={secretIds} onChange={(event) => setSecretIds(event.target.value)} placeholder="Secret ids comma-separated" />
        {secrets.length > 0 && <p>Available secret ids: {secrets.join(', ')}</p>}
        <Input value={configJson} onChange={(event) => setConfigJson(event.target.value)} placeholder='Config JSON (e.g. {"x":1})' />
        <Button
          disabled={!environmentId || createBinding.isPending}
          onClick={() => {
            if (!confirmProductionOperation(isProductionEnvironment, 'binding_create')) return;
            onSubmit();
          }}
        >
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
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!confirmProductionOperation(isProductionEnvironment, 'binding_transition')) return;
                    transitionBinding(binding.id, 'active');
                  }}
                  disabled={updateBindingStatus.isPending || transitionPendingByBinding[binding.id]}
                >
                  Update/Enable
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!confirmProductionOperation(isProductionEnvironment, 'binding_transition')) return;
                    transitionBinding(binding.id, 'disabled');
                  }}
                  disabled={updateBindingStatus.isPending || transitionPendingByBinding[binding.id]}
                >
                  Disable
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!confirmProductionOperation(isProductionEnvironment, 'binding_transition')) return;
                    transitionBinding(binding.id, 'retired');
                  }}
                  disabled={updateBindingStatus.isPending || transitionPendingByBinding[binding.id]}
                >
                  Retire
                </Button>
              </div>
            </div>
          ))}
        </div>

        <MutationError mutationError={createBinding.error} operation="binding_create" />
        <MutationError mutationError={updateBindingStatus.error} operation="binding_transition" />
      </CardContent>
    </Card>
  );
}

function BindingSwitchoverRow({
  bindingId,
  capability,
  currentProvider,
  isProductionEnvironment,
}: {
  bindingId: string;
  capability: string;
  currentProvider: string;
  isProductionEnvironment: boolean;
}) {
  const [targetProvider, setTargetProvider] = useState('');
  const [strategy, setStrategy] = useState('cutover');
  const [retirementStrategy, setRetirementStrategy] = useState('manual');
  const createSwitchover = useCreatePostBaseSwitchover(bindingId);
  const executeSwitchover = useExecutePostBaseSwitchover(bindingId);
  const { data } = usePostBaseBindingSwitchovers(bindingId);
  const pending = (data?.items ?? []).find((item) => item.status === 'pending' || item.status === 'failed');
  const preflight = pending?.execution_state_json?.preflight_report as Record<string, { ok?: boolean; detail?: string }> | undefined;
  const preflightBlocked = Boolean(preflight && Object.values(preflight).some((result) => result.ok === false));

  if (!pending) {
    return (
      <div className="space-y-2 rounded border border-gray-200 p-2 text-gray-500">
        <OperationGuardNotice operation="switchover_plan" isProductionEnvironment={isProductionEnvironment} />
        <div>{capability}: no pending switchover (current provider: {currentProvider})</div>
        <div className="flex flex-wrap items-center gap-2">
          <Input value={targetProvider} onChange={(event) => setTargetProvider(event.target.value)} placeholder="Target provider key" />
          <Input value={strategy} onChange={(event) => setStrategy(event.target.value)} placeholder="Strategy" />
          <Input value={retirementStrategy} onChange={(event) => setRetirementStrategy(event.target.value)} placeholder="Retirement strategy" />
          <Button
            size="sm"
            onClick={() => {
              if (!confirmProductionOperation(isProductionEnvironment, 'switchover_plan')) return;
              createSwitchover.mutate({ target_provider_key: targetProvider, strategy, retirement_strategy: retirementStrategy });
            }}
            disabled={createSwitchover.isPending || !targetProvider}
          >
            Plan switchover
          </Button>
        </div>
        <MutationError mutationError={createSwitchover.error} operation="switchover_plan" />
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
          <Button
            size="sm"
            onClick={() => {
              if (!confirmProductionOperation(isProductionEnvironment, 'switchover_execute')) return;
              executeSwitchover.mutate(pending.id);
            }}
            disabled={executeSwitchover.isPending || preflightBlocked}
          >
            {executeSwitchover.isPending ? 'Executing…' : 'Execute'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              if (!confirmProductionOperation(isProductionEnvironment, 'switchover_execute')) return;
              executeSwitchover.mutate(pending.id);
            }}
            disabled={executeSwitchover.isPending || preflightBlocked}
          >
            {pending.status === 'failed' ? 'Retry execute' : 'Rollback execute'}
          </Button>
        </div>
      </div>
      <OperationGuardNotice operation="switchover_execute" isProductionEnvironment={isProductionEnvironment} />
      {preflightBlocked ? (
        <p className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">
          Switchover execution blocked: clear preflight failures below before executing or retrying.
        </p>
      ) : null}

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

      <MutationError mutationError={executeSwitchover.error} operation="switchover_execute" />
    </div>
  );
}

function OperationGuardNotice({ operation, isProductionEnvironment = false }: { operation: HighRiskOperation; isProductionEnvironment?: boolean }) {
  return (
    <p className="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
      {HIGH_RISK_PREFLIGHT_COPY[operation]}
      {isProductionEnvironment ? ' Production stage: a manual confirmation is required before continuing.' : ''}
    </p>
  );
}

function MutationError({ mutationError, operation }: { mutationError: unknown; operation?: HighRiskOperation }) {
  if (!mutationError) {
    return null;
  }

  const message = extractMutationError(mutationError);
  const remediation = operation ? buildOperationRemediation(operation) : 'Review request payload, permissions, and dependent resource health.';
  return (
    <div className="space-y-1 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">
      <p>{message}</p>
      <p className="font-medium">Remediation: {remediation}</p>
    </div>
  );
}

function isPermissionDenied(error: unknown): boolean {
  const axiosError = error as AxiosError;
  return axiosError?.response?.status === 401 || axiosError?.response?.status === 403;
}

function extractMutationError(error: unknown): string {
  if (isPermissionDenied(error)) {
    return 'Permission restricted: your role cannot execute this operation.';
  }
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

export function buildOperationRemediation(operation: HighRiskOperation): string {
  switch (operation) {
    case 'binding_create':
    case 'binding_transition':
      return 'Confirm provider catalog support, validate secret references, and retry with a clear transition reason.';
    case 'secret_create':
    case 'secret_rotate':
    case 'secret_deactivate':
      return 'Validate secret scope/value, ensure no active dependency breakage, and retry after rotation/deactivation checks.';
    case 'webhook_drain':
    case 'webhook_recover':
      return 'Confirm queue health, resolve delivery failures, and rerun with operator approval if backlog pressure is acceptable.';
    case 'migration_apply':
    case 'migration_reconcile':
    case 'migration_retry':
      return 'Inspect migration error details, reconcile schema drift, then retry once environment readiness returns to healthy.';
    case 'switchover_plan':
    case 'switchover_execute':
      return 'Resolve preflight blockers, verify target provider readiness, and re-run under an operator-approved change window.';
    default:
      return 'Review payload and permission scope, then retry.';
  }
}
