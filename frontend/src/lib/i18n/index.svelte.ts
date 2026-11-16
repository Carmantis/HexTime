/**
 * Translation.
 *
 * No visible string is written into a component. Keys are English and grouped
 * by view, and a test checks that both bundles carry exactly the same set.
 */

import en from './en.json';
import fi from './fi.json';

export type Locale = 'fi' | 'en';

export const LOCALES: Locale[] = ['fi', 'en'];

type Bundle = Record<string, unknown>;

const bundles: Record<Locale, Bundle> = { fi, en };

const STORAGE_KEY = 'hextime.locale';

let current = $state<Locale>('fi');

/** Walk a dotted key such as "timer.start" into the bundle. */
function lookup(bundle: Bundle, key: string): string | undefined {
  const value = key
    .split('.')
    .reduce<unknown>((node, part) => (node as Bundle | undefined)?.[part], bundle);
  return typeof value === 'string' ? value : undefined;
}

/**
 * Translate a key. Reading `current` inside makes every call reactive, so a
 * language change re-renders the text without any extra plumbing.
 *
 * `{name}` placeholders are filled from `params`, e.g.
 * t('calendar.weekNumber', { n: 13 }) → "Vko 13".
 */
export function t(key: string, params?: Record<string, string | number>): string {
  // Fall back to Finnish, then to the key itself, so a missing translation is
  // visible in the UI rather than silently blank.
  const text = lookup(bundles[current], key) ?? lookup(bundles.fi, key) ?? key;
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    name in params ? String(params[name]) : placeholder,
  );
}

export const locale = {
  get current(): Locale {
    return current;
  },
  set current(next: Locale) {
    current = next;
    document.documentElement.lang = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Private windows and blocked site data: remembering is a convenience.
    }
  },
};

/** Pick the starting language: saved choice, else the OS/browser language. */
export function initLocale(fallback: string): void {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch {
    saved = null;
  }

  const browser = navigator.language?.slice(0, 2);
  const candidate = saved ?? (LOCALES.includes(browser as Locale) ? browser : fallback);

  locale.current = LOCALES.includes(candidate as Locale) ? (candidate as Locale) : 'fi';
}
