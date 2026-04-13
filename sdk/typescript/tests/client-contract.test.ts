import { describe, expect, it } from 'vitest';
import { PostBaseSdkClient } from '../src/client';

describe('generated TypeScript SDK contract', () => {
  it('routes requests through transport with operation paths', async () => {
    const calls: Array<{ method: string; path: string }> = [];
    const client = new PostBaseSdkClient({
      request: async (method, path) => {
        calls.push({ method, path });
        return { ok: true };
      },
    });

    await client.list_projects_api_v1_projects_get();
    await client.list_provider_catalog_api_v1_provider_catalog_get();

    expect(calls).toEqual([
      { method: 'GET', path: '/api/v1/projects' },
      { method: 'GET', path: '/api/v1/provider-catalog' },
    ]);
  });
});
