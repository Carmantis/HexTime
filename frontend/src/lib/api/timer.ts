import { api } from './client';
import type { TimeEntry, TimerStartInput } from './types';

/** The entry currently being timed, or null when nothing is running. */
export function fetchRunningTimer(): Promise<TimeEntry | null> {
  return api.get<TimeEntry | null>('/timer');
}

/** Start a timer. Any timer already running is stopped by the backend. */
export function startTimer(input: TimerStartInput = {}): Promise<TimeEntry> {
  return api.post<TimeEntry>('/timer/start', input);
}

/**
 * Stop the timer. `at` is the moment the user pressed Stop; it is sent when
 * the request is retried after an outage, so the entry ends at the click and
 * not whenever the server came back.
 */
export function stopTimer(at?: string): Promise<TimeEntry> {
  return api.post<TimeEntry>('/timer/stop', at ? { at } : {});
}
