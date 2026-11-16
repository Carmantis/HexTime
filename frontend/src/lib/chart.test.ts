import { describe, expect, it } from 'vitest';

import { hourAxis, hoursLabel } from './chart';

const HOUR = 3600;

describe('hourAxis', () => {
  it('steps in whole hours instead of round numbers of seconds', () => {
    // 16 h 30 min used to get ticks every 10 000 s ("2 h 47 min").
    expect(hourAxis(16.5 * HOUR, 5)).toEqual({ interval: 4 * HOUR, max: 20 * HOUR });
  });

  it('uses quarter hours for short totals', () => {
    expect(hourAxis(40 * 60, 4)).toEqual({ interval: 15 * 60, max: 45 * 60 });
  });

  it('ends exactly on the top value when it is a whole step', () => {
    expect(hourAxis(8 * HOUR, 4)).toEqual({ interval: 2 * HOUR, max: 8 * HOUR });
  });

  it('still draws an axis when there is no time at all', () => {
    expect(hourAxis(0, 4)).toEqual({ interval: 15 * 60, max: 15 * 60 });
  });

  it('keeps going past the largest step in the table', () => {
    const axis = hourAxis(5000 * HOUR, 4);
    expect(axis.interval % (500 * HOUR)).toBe(0);
    expect(axis.max / axis.interval).toBeLessThanOrEqual(4);
  });

  it('gives labels without minutes on hour steps', () => {
    const { interval } = hourAxis(16.5 * HOUR, 5);
    expect(hoursLabel(interval, 'fi')).toBe('4 t');
  });
});
