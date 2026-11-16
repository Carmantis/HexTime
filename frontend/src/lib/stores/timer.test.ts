import { describe, expect, it } from 'vitest';

import { ApiError } from '$lib/api/client';

import { isOutage } from './timer.svelte';

describe('isOutage', () => {
  it('counts no answer at all', () => {
    expect(isOutage(new ApiError('network_unavailable', 0, ''))).toBe(true);
  });

  it('counts the proxy saying the app is down', () => {
    expect(isOutage(new ApiError('unknown_error', 502, 'Bad Gateway'))).toBe(true);
    expect(isOutage(new ApiError('unknown_error', 503, ''))).toBe(true);
  });

  it('does not count an error the app itself reported', () => {
    expect(isOutage(new ApiError('email_failed', 502, ''))).toBe(false);
    expect(isOutage(new ApiError('timer_not_running', 409, ''))).toBe(false);
    expect(isOutage(new Error('boom'))).toBe(false);
  });
});
