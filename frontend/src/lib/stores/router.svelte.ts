/**
 * A hash router.
 *
 * The app is a single page served from "/" by FastAPI. Using the hash means
 * the backend never has to know about frontend routes, and the same build
 * works from a file-backed window as from a real host.
 *
 * A route may carry parameters after "?", as the links in emails do:
 * "#/set-password?token=…". Everything after "#" stays in the browser, so a
 * token in it never reaches a server or proxy log.
 */

export const ROUTES = [
  'tracking',
  'calendar',
  'reports',
  'projects',
  'teams',
  'admin',
  'settings',
] as const;

/** Server mode's sign-in pages. Reachable without being signed in. */
export const ACCOUNT_ROUTES = [
  'login',
  'forgot-password',
  'register',
  'set-password',
  'verify-email',
] as const;

export type Route = (typeof ROUTES)[number];
export type AccountRoute = (typeof ACCOUNT_ROUTES)[number];
export type AnyRoute = Route | AccountRoute;

const DEFAULT: Route = 'tracking';
const KNOWN: readonly string[] = [...ROUTES, ...ACCOUNT_ROUTES];

/** "#/set-password?token=abc" → route "set-password", params {token: "abc"}. */
export function parseHash(hash: string): { route: AnyRoute; params: URLSearchParams } {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?', 2);
  const route = KNOWN.includes(path) ? (path as AnyRoute) : DEFAULT;
  return { route, params: new URLSearchParams(query) };
}

let current = $state<AnyRoute>(DEFAULT);
let params = $state(new URLSearchParams());

export const router = {
  get current(): AnyRoute {
    return current;
  },
  get params(): URLSearchParams {
    return params;
  },
  /** True on a sign-in page, which shows instead of the app. */
  get isAccountPage(): boolean {
    return (ACCOUNT_ROUTES as readonly string[]).includes(current);
  },
};

export function navigate(route: AnyRoute): void {
  window.location.hash = `/${route}`;
}

function update(): void {
  ({ route: current, params } = parseHash(window.location.hash));
}

/** Start listening. Returns the unsubscribe function. */
export function initRouter(): () => void {
  update();
  window.addEventListener('hashchange', update);
  return () => window.removeEventListener('hashchange', update);
}
