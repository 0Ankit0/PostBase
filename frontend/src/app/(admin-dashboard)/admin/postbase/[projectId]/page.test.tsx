import { describe, expect, it } from 'vitest';
import type { AxiosError } from 'axios';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  buildReadinessRemediations,
  isReadinessHealthy,
  OperationStatusSummary,
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
});
