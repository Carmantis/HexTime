import { api, query } from './client';
import type { Tag } from './types';

export interface TagInput {
  name: string;
  color?: string;
}

export function fetchTags(includeArchived = false): Promise<Tag[]> {
  return api.get<Tag[]>(`/tags${query({ include_archived: includeArchived })}`);
}

/** With `teamId`, the team's tag (leads and admins only). */
export function createTag(input: TagInput, teamId: string | null = null): Promise<Tag> {
  return api.post<Tag>('/tags', { ...input, team_id: teamId });
}

export function updateTag(id: string, changes: Partial<TagInput>): Promise<Tag> {
  return api.patch<Tag>(`/tags/${id}`, changes);
}

export function archiveTag(id: string): Promise<Tag> {
  return api.post<Tag>(`/tags/${id}/archive`);
}

export function restoreTag(id: string): Promise<Tag> {
  return api.post<Tag>(`/tags/${id}/restore`);
}
