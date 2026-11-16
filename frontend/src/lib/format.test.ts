import { describe, expect, it } from 'vitest';

import {
  addDays,
  daysIn,
  formatClock,
  formatTimeOfDay,
  isoWeek,
  localDateKey,
  localMonthKey,
  monthWeeks,
  normalizeTime,
  rangeOf,
  startOfWeek,
} from './format';

describe('isoWeek', () => {
  it.each([
    [new Date(2026, 0, 1), 1, 'Thursday 1 January 2026 is in week 1'],
    [new Date(2024, 11, 30), 1, 'Monday 30 December 2024 is week 1 of 2025'],
    [new Date(2026, 11, 31), 53, '2026 starts on a Thursday, so it has 53 weeks'],
    [new Date(2027, 0, 3), 53, 'Sunday 3 January 2027 is still week 53 of 2026'],
    [new Date(2027, 0, 4), 1, 'Monday 4 January 2027 starts week 1'],
    [new Date(2026, 2, 23), 13, 'the week summer time starts'],
  ])('%s → %i (%s)', (date, week) => {
    expect(isoWeek(date)).toBe(week);
  });
});

describe('startOfWeek', () => {
  it('goes back to Monday', () => {
    expect(localDateKey(startOfWeek(new Date(2026, 2, 29)))).toBe('2026-03-23');
  });

  it('keeps a Monday where it is', () => {
    expect(localDateKey(startOfWeek(new Date(2026, 2, 23, 15, 30)))).toBe('2026-03-23');
  });

  it('starts at local midnight', () => {
    const monday = startOfWeek(new Date(2026, 2, 25, 15, 30));
    expect([monday.getHours(), monday.getMinutes()]).toEqual([0, 0]);
  });
});

describe('rangeOf', () => {
  it('a week is seven calendar days', () => {
    const { start, end } = rangeOf(new Date(2026, 2, 26), 'week');
    expect(localDateKey(start)).toBe('2026-03-23');
    expect(localDateKey(end)).toBe('2026-03-30');
  });

  it('a day ends at the next local midnight', () => {
    const { start, end } = rangeOf(new Date(2026, 4, 4, 13), 'day');
    expect(localDateKey(start)).toBe('2026-05-04');
    expect(localDateKey(end)).toBe('2026-05-05');
    expect(end.getHours()).toBe(0);
  });
});

describe('addDays', () => {
  it('counts calendar days across a month end', () => {
    expect(localDateKey(addDays(new Date(2026, 0, 30), 3))).toBe('2026-02-02');
  });
});

describe('formatClock', () => {
  it('pads every part', () => {
    expect(formatClock(3725)).toBe('01:02:05');
  });

  it('never shows a negative time', () => {
    expect(formatClock(-5)).toBe('00:00:00');
  });
});

describe('daysIn', () => {
  it('lists every day of a month, end excluded', () => {
    const { start, end } = rangeOf(new Date(2026, 1, 10), 'month');
    const days = daysIn(start, end).map(localDateKey);
    expect(days).toHaveLength(28);
    expect(days[0]).toBe('2026-02-01');
    expect(days.at(-1)).toBe('2026-02-28');
  });

  it('keeps one entry per day across the summer time change', () => {
    const { start, end } = rangeOf(new Date(2026, 2, 1), 'month');
    expect(daysIn(start, end)).toHaveLength(31);
  });
});

describe('localMonthKey', () => {
  it('pads the month to two digits', () => {
    expect(localMonthKey(new Date(2026, 2, 31))).toBe('2026-03');
  });
});

describe('monthWeeks', () => {
  it('starts on the Monday before the 1st', () => {
    // 1 March 2026 is a Sunday, so the grid opens on Monday 23 February.
    const weeks = monthWeeks(new Date(2026, 2, 15)).map(localDateKey);
    expect(weeks[0]).toBe('2026-02-23');
    expect(weeks.at(-1)).toBe('2026-03-30');
    expect(weeks).toHaveLength(6);
  });

  it('needs only four rows for a February that starts on a Monday', () => {
    expect(monthWeeks(new Date(2027, 1, 1))).toHaveLength(4);
  });
});

describe('normalizeTime', () => {
  it('reads the ways people type a time', () => {
    expect(normalizeTime('09:30')).toBe('09:30');
    expect(normalizeTime('9:30')).toBe('09:30');
    expect(normalizeTime('9.30')).toBe('09:30');
    expect(normalizeTime('930')).toBe('09:30');
    expect(normalizeTime('2359')).toBe('23:59');
    expect(normalizeTime('9')).toBe('09:00');
    expect(normalizeTime(' 17 ')).toBe('17:00');
  });

  it('refuses what is not a time on a 24-hour clock', () => {
    for (const text of ['', '24:00', '9:60', '9:5', 'abc', '9 am', '12345']) {
      expect(normalizeTime(text)).toBeNull();
    }
  });
});

describe('formatTimeOfDay', () => {
  it('uses the 24-hour clock in English too', () => {
    const afternoon = new Date(2026, 9, 25, 15, 5).toISOString();
    const midnight = new Date(2026, 9, 25, 0, 5).toISOString();
    expect(formatTimeOfDay(afternoon, 'en')).toBe('15:05');
    expect(formatTimeOfDay(midnight, 'en')).toBe('00:05');
  });
});
