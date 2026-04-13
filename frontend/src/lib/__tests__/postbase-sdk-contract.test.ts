import { describe, expect, it } from 'vitest';
import type { PostBaseProviderCatalogRead } from '@/types';

describe('PostBase SDK compatibility fixtures', () => {
  it('accepts provider catalog fixture shape used by SDK clients', () => {
    const fixture: PostBaseProviderCatalogRead = {
      id: 'provider-1',
      capability_key: 'storage',
      provider_key: 's3-compatible',
      adapter_version: '1.0.0',
      certification_state: 'certified',
      metadata_json: {
        conformance: {
          state: 'pending',
          badge: 'unknown',
          last_report_path: 'backend/artifacts/provider-conformance.json',
        },
      },
    };

    expect(fixture.metadata_json).toHaveProperty('conformance');
  });
});
