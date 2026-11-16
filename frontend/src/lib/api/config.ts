import { api } from './client';
import type { AppConfig } from './types';

/** What mode the backend is running in. Read once at startup. */
export function fetchConfig(): Promise<AppConfig> {
  return api.get<AppConfig>('/config');
}
