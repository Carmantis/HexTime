/**
 * What the backend told us about itself.
 *
 * The frontend never hardcodes the mode: it asks at startup and hides the
 * server-only parts of the UI accordingly.
 */

import { fetchConfig } from '$lib/api/config';
import type { AppConfig } from '$lib/api/types';

let config = $state<AppConfig | null>(null);
let failure = $state<string | null>(null);

export const appConfig = {
  get current(): AppConfig | null {
    return config;
  },
  get failure(): string | null {
    return failure;
  },
  /** Server-only features are hidden until the backend says otherwise. */
  get isServer(): boolean {
    return config?.mode === 'server';
  },
};

export async function loadConfig(): Promise<void> {
  failure = null;
  try {
    config = await fetchConfig();
  } catch (error) {
    config = null;
    failure = error instanceof Error ? error.message : 'unknown_error';
  }
}
