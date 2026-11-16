/**
 * Formatting for display only.
 *
 * Times arrive from the backend as UTC and are converted to local time here
 * and nowhere else. The clock is always 24-hour.
 */

/** Seconds as HH:MM:SS, for the running timer. Always monospace on screen. */
export function formatClock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const parts = [Math.floor(seconds / 3600), Math.floor((seconds % 3600) / 60), seconds % 60];
  return parts.map((part) => String(part).padStart(2, '0')).join(':');
}

/** Seconds as "1 h 30 min", for totals. */
export function formatDuration(totalSeconds: number, locale: string): string {
  const minutes = Math.round(Math.max(0, totalSeconds) / 60);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;

  const hourUnit = locale === 'fi' ? 't' : 'h';
  if (hours === 0) return `${rest} min`;
  if (rest === 0) return `${hours} ${hourUnit}`;
  return `${hours} ${hourUnit} ${rest} min`;
}

/** An ISO instant as a local time of day, e.g. "09:30". */
export function formatTimeOfDay(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
    // 24-hour clock in every language. Not hour12: false, which some engines
    // turn into "24:05" just after midnight.
    hourCycle: 'h23',
  }).format(new Date(iso));
}

/** An ISO instant as the value a <input type="date"> expects, in local time. */
export function toDateInput(iso: string): string {
  const date = new Date(iso);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

/**
 * What someone typed into a time field, as "HH:MM" on a 24-hour clock, or
 * null if it is not a time. Accepts "9:30", "9.30", "930", "0930" and "9".
 */
export function normalizeTime(text: string): string | null {
  const trimmed = text.trim();
  const separated = /^(\d{1,2})[:.](\d{2})$/.exec(trimmed);
  let hours: string;
  let minutes: string;
  if (separated) {
    [, hours, minutes] = separated;
  } else if (/^\d{3,4}$/.test(trimmed)) {
    hours = trimmed.slice(0, -2);
    minutes = trimmed.slice(-2);
  } else if (/^\d{1,2}$/.test(trimmed)) {
    hours = trimmed;
    minutes = '00';
  } else {
    return null;
  }
  if (Number(hours) > 23 || Number(minutes) > 59) return null;
  return `${hours.padStart(2, '0')}:${minutes}`;
}

/** An ISO instant as "HH:MM" in local time, the value of a time field. */
export function toTimeInput(iso: string): string {
  const date = new Date(iso);
  return [
    String(date.getHours()).padStart(2, '0'),
    String(date.getMinutes()).padStart(2, '0'),
  ].join(':');
}

/**
 * The two form inputs back into an instant the API accepts.
 *
 * The inputs are local time, which is the only form a person can reason about.
 * toISOString() converts to UTC, which is the only form the database stores.
 */
export function fromDateAndTime(date: string, time: string): string {
  return new Date(`${date}T${time}`).toISOString();
}

export type RangeMode = 'day' | 'week' | 'month' | 'year';

/** Local midnight at the start of `date`'s day. */
export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/**
 * `days` calendar days later, at the same local wall-clock time.
 *
 * setDate() counts calendar days, not 24-hour blocks, which is what keeps a
 * week seven days long across a daylight saving change.
 */
export function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

/** Monday 00:00 of the week containing `date`. Weeks start on Monday. */
export function startOfWeek(date: Date): Date {
  const day = startOfDay(date);
  const sinceMonday = (day.getDay() + 6) % 7;
  return addDays(day, -sinceMonday);
}

/** The ISO 8601 week number: week 1 is the one containing the first Thursday. */
export function isoWeek(date: Date): number {
  const thursday = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const weekday = thursday.getUTCDay() || 7;
  thursday.setUTCDate(thursday.getUTCDate() + 4 - weekday);
  const yearStart = Date.UTC(thursday.getUTCFullYear(), 0, 1);
  return Math.ceil(((thursday.getTime() - yearStart) / 86_400_000 + 1) / 7);
}

/** Local midnight on the first day of `date`'s month. */
export function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

/** Local midnight on 1 January of `date`'s year. */
export function startOfYear(date: Date): Date {
  return new Date(date.getFullYear(), 0, 1);
}

/**
 * The half-open [start, end) range a view shows.
 *
 * Months and years are stepped with the calendar rather than by adding days,
 * so a 28-day February and a leap year both come out right.
 */
export function rangeOf(anchor: Date, mode: RangeMode): { start: Date; end: Date } {
  switch (mode) {
    case 'day':
      return { start: startOfDay(anchor), end: addDays(startOfDay(anchor), 1) };
    case 'week':
      return { start: startOfWeek(anchor), end: addDays(startOfWeek(anchor), 7) };
    case 'month': {
      const start = startOfMonth(anchor);
      return { start, end: new Date(start.getFullYear(), start.getMonth() + 1, 1) };
    }
    case 'year': {
      const start = startOfYear(anchor);
      return { start, end: new Date(start.getFullYear() + 1, 0, 1) };
    }
  }
}

/** One period later or earlier, stepping by whole months and years. */
export function shiftRange(anchor: Date, mode: RangeMode, direction: -1 | 1): Date {
  switch (mode) {
    case 'day':
      return addDays(anchor, direction);
    case 'week':
      return addDays(anchor, direction * 7);
    case 'month':
      return new Date(anchor.getFullYear(), anchor.getMonth() + direction, 1);
    case 'year':
      return new Date(anchor.getFullYear() + direction, 0, 1);
  }
}

/** Every local day in the half-open range [start, end), one Date per day. */
export function daysIn(start: Date, end: Date): Date[] {
  const days: Date[] = [];
  for (let day = start; day < end; day = addDays(day, 1)) {
    days.push(day);
  }
  return days;
}

/**
 * The Mondays of the weeks a month grid shows: from the week containing the
 * 1st to the week containing the last day, so a month spans four to six rows.
 */
export function monthWeeks(date: Date): Date[] {
  const { start, end } = rangeOf(date, 'month');
  const weeks: Date[] = [];
  for (let monday = startOfWeek(start); monday < end; monday = addDays(monday, 7)) {
    weeks.push(monday);
  }
  return weeks;
}

/** "2026-03-29" for the local day of `date` — the backend's day-group key. */
export function localDateKey(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

/** "2026-03" for the local month of `date` — the backend's month-group key. */
export function localMonthKey(date: Date): string {
  return localDateKey(date).slice(0, 7);
}

/** The IANA zone the browser runs in, e.g. "Europe/Helsinki". */
export function localTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** The local day containing `date`, as the half-open range the API expects. */
export function dayRange(date: Date): { from: string; to: string } {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { from: start.toISOString(), to: end.toISOString() };
}
