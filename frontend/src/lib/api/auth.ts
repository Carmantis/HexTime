import { api } from './client';
import type { Me, MeUpdate, TokenInfo } from './types';

/** Who the frontend is talking as. 401 in server mode when nobody is signed in. */
export function fetchMe(): Promise<Me> {
  return api.get<Me>('/auth/me');
}

export function login(email: string, password: string): Promise<Me> {
  return api.post<Me>('/auth/login', { email, password });
}

export function logout(): Promise<void> {
  return api.post<void>('/auth/logout');
}

/** What an emailed link is for. POST so the token stays out of server logs. */
export function inspectToken(token: string): Promise<TokenInfo> {
  return api.post<TokenInfo>('/auth/token', { token });
}

/** Use a setup or reset link: sets the password and signs in. */
export function setPassword(token: string, password: string): Promise<Me> {
  return api.post<Me>('/auth/password/set', { token, password });
}

/** Always succeeds: the answer never says whether the address has an account. */
export function forgotPassword(email: string): Promise<void> {
  return api.post<void>('/auth/password/forgot', { email });
}

/** Sign up; the email that follows brings a link for choosing the password. */
export function register(email: string, displayName: string): Promise<void> {
  return api.post<void>('/auth/register', { email, display_name: displayName });
}

export function verifyEmail(token: string): Promise<void> {
  return api.post<void>('/auth/verify-email', { token });
}

export function updateMe(changes: MeUpdate): Promise<Me> {
  return api.patch<Me>('/me', changes);
}
