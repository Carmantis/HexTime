import { describe, expect, it } from 'vitest';

import { parseHash } from './router.svelte';

describe('parseHash', () => {
  it('reads a plain route', () => {
    expect(parseHash('#/reports').route).toBe('reports');
  });

  it('reads the token from an emailed link', () => {
    const { route, params } = parseHash('#/set-password?token=abc-123_XYZ');
    expect(route).toBe('set-password');
    expect(params.get('token')).toBe('abc-123_XYZ');
  });

  it('falls back to tracking for anything unknown', () => {
    expect(parseHash('').route).toBe('tracking');
    expect(parseHash('#/nowhere?x=1').route).toBe('tracking');
  });
});
