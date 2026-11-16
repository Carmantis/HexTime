/**
 * The projects and teams the pickers offer (the timer bar, the entry form).
 *
 * One shared copy instead of each picker fetching its own, so that one
 * refresh updates them all. It goes stale when the user joins or leaves a
 * team, or when a project is created, renamed or archived (by them, or in a
 * team by its lead on another device); callers that cause such a change call
 * refreshPicker(), and the timer bar also refreshes when the window regains
 * focus.
 */

import { fetchProjects } from '$lib/api/projects';
import { fetchTeams } from '$lib/api/teams';
import type { Project, Team } from '$lib/api/types';
import { appConfig } from '$lib/stores/config.svelte';

let projects = $state<Project[]>([]);
let teams = $state<Team[]>([]);

export const picker = {
  /** Active projects the user may book time on: own and their teams'. */
  get projects(): Project[] {
    return projects;
  },
  /** The user's teams, to name the groups (server mode; empty locally). */
  get teams(): Team[] {
    return teams;
  },
};

/**
 * Counts refreshes, so a slow older answer cannot overwrite a newer one: an
 * answer is kept only if no later request has answered yet. (Not only the
 * latest request's: if that one fails, an earlier success still counts.)
 */
let sent = 0;
let applied = 0;

export async function refreshPicker(): Promise<void> {
  const request = ++sent;
  try {
    const [loadedProjects, loadedTeams] = await Promise.all([
      fetchProjects(),
      appConfig.isServer ? fetchTeams() : Promise.resolve([]),
    ]);
    // E.g. the team's projects, fetched just before the user left the team.
    if (request < applied) return;
    applied = request;
    projects = loadedProjects;
    teams = loadedTeams;
  } catch {
    // Keep the old lists: a picker with stale options beats an empty one.
  }
}
