/**
 * Who is signed in.
 *
 * Asked once at startup from /auth/me, which answers in both modes: local
 * mode always has its one desktop user, so the app never shows a sign-in page
 * there. In server mode a 401 from *any* request (an expired session, a
 * sign-out on another device) clears the user, and the app shows the sign-in
 * page in place of whatever was on screen.
 */

import { fetchMe, logout } from '$lib/api/auth';
import { setUnauthorizedHandler } from '$lib/api/client';
import type { Me } from '$lib/api/types';
import { navigate } from '$lib/stores/router.svelte';

let user = $state<Me | null>(null);
let checked = $state(false);

export const session = {
  get user(): Me | null {
    return user;
  },
  /** False until the first /auth/me has answered: show nothing yet. */
  get checked(): boolean {
    return checked;
  },
  get signedIn(): boolean {
    return user !== null;
  },
};

setUnauthorizedHandler(() => {
  user = null;
});

export async function loadSession(): Promise<void> {
  try {
    user = await fetchMe();
  } catch {
    user = null;
  } finally {
    checked = true;
  }
}

/** After a login or a password set through a link. */
export function signedIn(me: Me): void {
  user = me;
}

/** After the profile was edited. */
export function updateUser(me: Me): void {
  user = me;
}

export async function signOut(): Promise<void> {
  try {
    await logout();
  } catch {
    // Signed out locally regardless: the cookie is gone or will expire.
  }
  user = null;
  navigate('login');
}
