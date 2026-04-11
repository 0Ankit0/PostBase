import { describe, expect, it } from 'vitest';
import type { AxiosError } from 'axios';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  buildOperationRemediation,
  buildReadinessRemediations,
  deriveQuerySurfaceState,
  isReadinessHealthy,
  OperationStatusSummary,
  resolveSelectedEnvironmentId,
  shouldRequireProductionConfirmation,
} from './page';

function createAxiosError(status: number): AxiosError {
  return {
    name: 'AxiosError',
    message: 'Request failed',
    config: { headers: {} as never },
    isAxiosError: true,
    toJSON: () => ({}),
    response: {
      status,
      statusText: '',
      headers: {},
      config: { headers: {} as never },
      data: {},
    },
  } as AxiosError;
}

describe('PostBase admin control plane helpers', () => {
  it('builds actionable readiness remediations from failure details', () => {
    const remediations = buildReadinessRemediations('Secret rotation required due to schema drift');

    expect(remediations).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ reason: 'Credentials are missing or invalid' }),
        expect.objectContaining({ reason: 'Schema migration drift detected' }),
      ]),
    );
    expect(isReadinessHealthy('degraded')).toBe(false);
  });

  it('falls back to generic remediation when no keyword matches', () => {
    const remediations = buildReadinessRemediations('custom readiness issue');

    expect(remediations).toEqual([
      {
        reason: 'Validation checks did not pass',
        remediation: 'Review capability health and execute the suggested run-now operational jobs.',
      },
    ]);
    expect(isReadinessHealthy('ready')).toBe(true);
  });

  it('shows permission-restricted status when action is blocked', () => {
    const markup = renderToStaticMarkup(
      <OperationStatusSummary
        latestOperationSummary="Webhook drain complete: 3 job(s) drained."
        drainError={createAxiosError(403)}
        recoverError={null}
        reconcileError={null}
        lastPolledAt="2026-04-09T00:00:00Z"
      />,
    );

    expect(markup).toContain('Permission-restricted for one or more actions.');
    expect(markup).toContain('Webhook drain complete: 3 job(s) drained.');
    expect(markup).toContain('Latest reconciliation poll:');
  });

  it('derives loading, success, error, and stale-cache query states', () => {
    expect(
      deriveQuerySurfaceState({
        isPending: true,
        isError: false,
        hasData: false,
      }),
    ).toBe('loading');

    expect(
      deriveQuerySurfaceState({
        isPending: false,
        isError: false,
        hasData: true,
      }),
    ).toBe('success');

    expect(
      deriveQuerySurfaceState({
        isPending: false,
        isError: true,
        hasData: false,
      }),
    ).toBe('error');

    expect(
      deriveQuerySurfaceState({
        isPending: false,
        isError: true,
        hasData: true,
      }),
    ).toBe('stale-cache');
  });

  it('returns actionable remediation guidance for high-risk operations', () => {
    expect(buildOperationRemediation('migration_apply')).toContain('reconcile schema drift');
    expect(buildOperationRemediation('switchover_execute')).toContain('Resolve preflight blockers');
  });

  it('resolves selected environment from URL query when valid and falls back to first environment when invalid', () => {
    const environments = [
      {
        id: 'env-dev',
        project_id: 'project-1',
        name: 'Development',
        slug: 'development',
        stage: 'development',
        region_preference: null,
        status: 'active',
        readiness_state: 'ready',
        readiness_detail: 'Ready',
        last_validated_at: null,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'env-prod',
        project_id: 'project-1',
        name: 'Production',
        slug: 'production',
        stage: 'production',
        region_preference: null,
        status: 'active',
        readiness_state: 'ready',
        readiness_detail: 'Ready',
        last_validated_at: null,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ] as const;

    expect(resolveSelectedEnvironmentId([...environments], 'env-prod')).toBe('env-prod');
    expect(resolveSelectedEnvironmentId([...environments], 'missing-env')).toBe('env-dev');
    expect(resolveSelectedEnvironmentId([...environments], null)).toBe('env-dev');
  });

  it('requires confirmations only for production-stage operations', () => {
    expect(shouldRequireProductionConfirmation('production')).toBe(true);
    expect(shouldRequireProductionConfirmation('staging')).toBe(false);
    expect(shouldRequireProductionConfirmation('development')).toBe(false);
    expect(shouldRequireProductionConfirmation(undefined)).toBe(false);
  });
});
