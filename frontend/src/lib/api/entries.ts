import { api, query } from './client';
import type { TimeEntry, TimeEntryInput } from './types';

export interface EntryFilter {
  /** ISO 8601 instants. The backend rejects a timestamp without an offset. */
  from?: string;
  to?: string;
  project_id?: string;
}

export function fetchEntries(filter: EntryFilter = {}): Promise<TimeEntry[]> {
  return api.get<TimeEntry[]>(`/entries${query({ ...filter })}`);
}

export function fetchEntry(id: string): Promise<TimeEntry> {
  return api.get<TimeEntry>(`/entries/${id}`);
}

export function createEntry(input: TimeEntryInput): Promise<TimeEntry> {
  return api.post<TimeEntry>('/entries', input);
}

/**
 * Send only the fields that should change. A key left out is untouched;
 * a key set to null clears the field, where the field allows it.
 */
export function updateEntry(id: string, changes: Partial<TimeEntryInput>): Promise<TimeEntry> {
  return api.patch<TimeEntry>(`/entries/${id}`, changes);
}

export function deleteEntry(id: string): Promise<void> {
  return api.remove(`/entries/${id}`);
}
