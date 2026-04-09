import { describe, expect, it } from 'vitest';
import { resolvePostBaseContextKey } from './use-postbase';

describe('use-postbase context scoping', () => {
  it('falls back to personal context when tenant is missing', () => {
    expect(resolvePostBaseContextKey(undefined)).toBe('personal');
    expect(resolvePostBaseContextKey(null)).toBe('personal');
  });

  it('uses tenant id when provided to isolate cache scope', () => {
    expect(resolvePostBaseContextKey('tenant_alpha')).toBe('tenant_alpha');
    expect(resolvePostBaseContextKey('tenant_beta')).not.toBe(resolvePostBaseContextKey('tenant_alpha'));
  });
});
