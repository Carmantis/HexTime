/**
 * Light and dark.
 *
 * The theme is an attribute on <html>, which is what tokens.css switches on.
 * index.html already stamps `dark`, so the window never flashes light before
 * this runs.
 *
 * The choice is kept in localStorage on this device. In server mode the
 * account remembers it too (Settings saves it with PATCH /me), so it follows
 * the user to another device.
 */

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'hextime.theme';

let current = $state<Theme>('dark');

function apply(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

export const theme = {
  get current(): Theme {
    return current;
  },
  set current(next: Theme) {
    current = next;
    apply(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Remembering the theme is a convenience, never a requirement.
    }
  },
};

export function toggleTheme(): void {
  theme.current = current === 'dark' ? 'light' : 'dark';
}

/** Restore the saved theme, defaulting to dark. */
export function initTheme(): void {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch {
    saved = null;
  }
  theme.current = saved === 'light' ? 'light' : 'dark';
}
