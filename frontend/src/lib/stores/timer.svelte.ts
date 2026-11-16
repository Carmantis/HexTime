/**
 * The running timer.
 *
 * Only the entry itself lives here. The ticking clock belongs to the component
 * showing it, so no interval keeps running when nothing is on screen.
 */

import { ApiError } from '$lib/api/client';
import { fetchRunningTimer, startTimer, stopTimer } from '$lib/api/timer';
import type { TimeEntry, TimerStartInput } from '$lib/api/types';

let running = $state<TimeEntry | null>(null);
let busy = $state(false);
let errorCode = $state<string | null>(null);
let retrying = $state(false);

/** How often, and for how long, a stop that did not get through is retried. */
const RETRY_EVERY_MS = 2000;
/** Matches the backend's limit on how far back a stop may be dated. */
const RETRY_FOR_MS = 10 * 60 * 1000;

export const timer = {
  get running(): TimeEntry | null {
    return running;
  },
  get isRunning(): boolean {
    return running !== null;
  },
  get busy(): boolean {
    return busy;
  },
  /** An error *code*, for the UI to translate. Never a raw message. */
  get errorCode(): string | null {
    return errorCode;
  },
  /** A stop is waiting for the server to come back. */
  get retrying(): boolean {
    return retrying;
  },
};

/**
 * The server could not be reached: no answer at all, or the proxy in front
 * of it saying the app is down for a moment (a restart during an update).
 * An error the app itself reported, even with a 5xx status, is not this.
 */
export function isOutage(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.code === 'network_unavailable') return true;
  return error.code === 'unknown_error' && [502, 503, 504].includes(error.status);
}

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function run<T>(action: () => Promise<T>): Promise<T | null> {
  busy = true;
  errorCode = null;
  try {
    return await action();
  } catch (error) {
    errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    return null;
  } finally {
    busy = false;
  }
}

export async function refreshTimer(): Promise<void> {
  const entry = await run(fetchRunningTimer);
  running = entry ?? null;
}

export async function start(input: TimerStartInput = {}): Promise<void> {
  const entry = await run(() => startTimer(input));
  if (entry) running = entry;
}

/**
 * Stop the timer. If the server cannot be reached, keep trying with the time
 * of the click, so a brief outage does not add its length to the entry.
 */
export async function stop(): Promise<void> {
  const clickedAt = new Date();
  busy = true;
  errorCode = null;
  try {
    for (;;) {
      try {
        await stopTimer(retrying ? clickedAt.toISOString() : undefined);
        running = null;
        return;
      } catch (error) {
        if (!isOutage(error) || Date.now() - clickedAt.getTime() > RETRY_FOR_MS) throw error;
        retrying = true;
        await pause(RETRY_EVERY_MS);
      }
    }
  } catch (error) {
    errorCode = error instanceof ApiError ? error.code : 'unknown_error';
  } finally {
    retrying = false;
    busy = false;
  }
}

export function clearTimerError(): void {
  errorCode = null;
}
