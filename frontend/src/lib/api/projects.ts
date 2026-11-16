import { api, query } from './client';
import type { Project, Task } from './types';

export interface ProjectInput {
  name: string;
  color?: string;
  client_name?: string | null;
  billable_default?: boolean;
  hourly_rate_cents?: number | null;
  currency?: string;
}

export function fetchProjects(includeArchived = false): Promise<Project[]> {
  return api.get<Project[]>(`/projects${query({ include_archived: includeArchived })}`);
}

export function fetchProject(id: string): Promise<Project> {
  return api.get<Project>(`/projects/${id}`);
}

/** With `teamId`, the team's project (leads and admins only). */
export function createProject(input: ProjectInput, teamId: string | null = null): Promise<Project> {
  return api.post<Project>('/projects', { ...input, team_id: teamId });
}

export function updateProject(id: string, changes: Partial<ProjectInput>): Promise<Project> {
  return api.patch<Project>(`/projects/${id}`, changes);
}

/** Archived, never deleted, so old entries keep their project. */
export function archiveProject(id: string): Promise<Project> {
  return api.post<Project>(`/projects/${id}/archive`);
}

export function restoreProject(id: string): Promise<Project> {
  return api.post<Project>(`/projects/${id}/restore`);
}

export function fetchTasks(projectId: string, includeArchived = false): Promise<Task[]> {
  return api.get<Task[]>(
    `/projects/${projectId}/tasks${query({ include_archived: includeArchived })}`,
  );
}

export function createTask(projectId: string, name: string): Promise<Task> {
  return api.post<Task>(`/projects/${projectId}/tasks`, { name });
}

export function updateTask(taskId: string, name: string): Promise<Task> {
  return api.patch<Task>(`/tasks/${taskId}`, { name });
}

export function archiveTask(taskId: string): Promise<Task> {
  return api.post<Task>(`/tasks/${taskId}/archive`);
}
