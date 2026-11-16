import { api } from './client';
import type { AddResult, AdminUser } from './types';
import type { PastedPerson } from '$lib/people';

export function fetchUsers(): Promise<AdminUser[]> {
  return api.get<AdminUser[]>('/admin/users');
}

/** Invite everyone; one result per person, even when some fail. */
export async function addPeople(people: PastedPerson[]): Promise<AddResult[]> {
  const body = await api.post<{ results: AddResult[] }>('/admin/users', { people });
  return body.results;
}

/** A fresh link: to set a password, or to reset it if there is one. */
export function sendLink(userId: string): Promise<void> {
  return api.post<void>(`/admin/users/${userId}/send-link`);
}

export function updateUser(
  userId: string,
  changes: { is_active?: boolean; is_admin?: boolean },
): Promise<AdminUser> {
  return api.patch<AdminUser>(`/admin/users/${userId}`, changes);
}
