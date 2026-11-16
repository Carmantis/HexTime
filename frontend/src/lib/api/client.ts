/**
 * The one place that speaks HTTP.
 *
 * Components never call `fetch` themselves. URLs are always relative, so the
 * same build works in the pywebview window, behind Caddy and through the Vite
 * dev proxy without knowing which it is.
 */

const BASE = '/api/v1';

/**
 * Sent with every request. In server mode the backend refuses a change
 * without it: a page on another site cannot add a custom header, so this
 * proves the request came from HexTime's own pages (CSRF protection).
 */
const CSRF_HEADER = { 'X-HexTime-CSRF': '1' };

let onUnauthorized: (() => void) | null = null;

/**
 * Called whenever the backend answers 401: the session has expired or was
 * ended elsewhere. The session store uses it to show the sign-in page.
 */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

/** The single error shape the backend promises for every failure. */
interface ErrorEnvelope {
  error: { code: string; message: string; fields?: string[] };
}

/**
 * A failure the backend described. `code` is what the UI translates — the
 * `message` is for developers and never shown to the user as-is.
 */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    message: string,
    readonly fields: string[] = [],
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Send a request; a failure of any kind comes back as an ApiError. */
async function send(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...CSRF_HEADER, ...init.headers },
    });
  } catch {
    // The backend is not answering at all — in local mode it shares the
    // process, so this usually means it is still starting up.
    throw new ApiError('network_unavailable', 0, 'the backend did not answer');
  }

  if (response.status === 401) {
    onUnauthorized?.();
  }

  if (!response.ok) {
    // Errors are JSON even from routes that answer with a file.
    const body: unknown = await response.json().catch(() => null);
    const envelope = (body as ErrorEnvelope | null)?.error;
    throw new ApiError(
      envelope?.code ?? 'unknown_error',
      response.status,
      envelope?.message ?? response.statusText,
      envelope?.fields ?? [],
    );
  }

  return response;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await send(path, init);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** A file the backend sent, with the name it suggested. */
export interface DownloadedFile {
  blob: Blob;
  filename: string;
}

/** The filename="..." part of a Content-Disposition header. */
export function filenameFrom(disposition: string | null, fallback: string): string {
  return disposition?.match(/filename="([^"]+)"/)?.[1] ?? fallback;
}

async function download(path: string, fallbackName: string): Promise<DownloadedFile> {
  const response = await send(path);
  return {
    blob: await response.blob(),
    filename: filenameFrom(response.headers.get('Content-Disposition'), fallbackName),
  };
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  remove: (path: string) => request<void>(path, { method: 'DELETE' }),
  download,
};

/** Build a query string, leaving out anything not given. */
export function query(params: Record<string, string | number | boolean | undefined>): string {
  const pairs = Object.entries(params).filter(([, value]) => value !== undefined);
  return pairs.length ? `?${new URLSearchParams(pairs.map(([k, v]) => [k, String(v)]))}` : '';
}
