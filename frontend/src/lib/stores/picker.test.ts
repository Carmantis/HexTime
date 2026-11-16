import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Project, Team } from '$lib/api/types';

/** Each request waits until the test answers it, in whatever order. */
interface Pending {
  resolve: (projects: Project[]) => void;
  reject: (error: Error) => void;
}
let pending: Pending[] = [];
const teamsByRequest: Team[][] = [];

vi.mock('$lib/api/projects', () => ({
  fetchProjects: () =>
    new Promise<Project[]>((resolve, reject) => {
      pending.push({ resolve, reject });
    }),
}));
vi.mock('$lib/api/teams', () => ({
  fetchTeams: () => Promise.resolve(teamsByRequest.shift() ?? []),
}));
vi.mock('$lib/stores/config.svelte', () => ({ appConfig: { isServer: true } }));

const { picker, refreshPicker } = await import('./picker.svelte');

const project = (name: string): Project => ({ id: name, name }) as Project;
const team = (name: string): Team => ({ id: name, name }) as Team;
const names = (rows: Array<{ name: string }>): string[] => rows.map((row) => row.name);

beforeEach(() => {
  pending = [];
});

describe('refreshPicker', () => {
  it('keeps the newer answer when an older one arrives last', async () => {
    // Before leaving the team, then after.
    teamsByRequest.push([team('Web')], []);
    const before = refreshPicker();
    const after = refreshPicker();

    pending[1].resolve([project('own')]);
    await after;
    pending[0].resolve([project('own'), project("Web's")]);
    await before;

    expect(names(picker.projects)).toEqual(['own']);
    expect(picker.teams).toEqual([]);
  });

  it('still takes an older answer when the newer request fails', async () => {
    teamsByRequest.push([], []);
    const first = refreshPicker();
    const second = refreshPicker();

    pending[1].reject(new Error('offline'));
    await second;
    pending[0].resolve([project('fresh')]);
    await first;

    expect(names(picker.projects)).toEqual(['fresh']);
  });
});
