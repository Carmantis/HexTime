/**
 * Team rules the UI needs to know about, mirroring services/ownership.py.
 *
 * Only for showing the right controls: the backend checks every one of these
 * again and is what actually decides.
 */

import type { Team, TeamRole } from '$lib/api/types';

/** Leads run a team, its projects and tags included. */
export function isManager(role: TeamRole | null | undefined): boolean {
  return role === 'lead';
}

/** Teams where the user may create projects and tags. */
export function managedTeams(teams: Team[]): Team[] {
  return teams.filter((team) => isManager(team.role));
}

/** Own rows always; a team's only as its lead. */
export function canChange(row: { owner_team_id: string | null }, teams: Team[]): boolean {
  if (row.owner_team_id === null) return true;
  return isManager(teams.find((team) => team.id === row.owner_team_id)?.role);
}

export function teamName(teamId: string | null, teams: Team[]): string | null {
  if (teamId === null) return null;
  return teams.find((team) => team.id === teamId)?.name ?? null;
}

export interface ProjectGroup<P> {
  /** null for the user's own projects; otherwise the owning team. */
  teamId: string | null;
  /** The team's name; null for own projects (the picker labels those). */
  teamName: string | null;
  projects: P[];
}

/**
 * Split a project list into the user's own and one group per team, so a
 * picker can show whose project is whose. Own projects come first, then the
 * teams by name; each group keeps the order it was given (the API sorts by
 * name). Empty groups are left out.
 *
 * A team project whose team is not in `teams` (the list has not caught up
 * yet) still gets a group of its own, without a name, rather than vanishing.
 */
export function groupProjects<P extends { owner_team_id: string | null }>(
  projects: P[],
  teams: Team[],
): ProjectGroup<P>[] {
  const own: P[] = [];
  const byTeam = new Map<string, P[]>();
  for (const project of projects) {
    if (project.owner_team_id === null) {
      own.push(project);
    } else {
      const list = byTeam.get(project.owner_team_id) ?? [];
      list.push(project);
      byTeam.set(project.owner_team_id, list);
    }
  }

  const teamGroups = [...byTeam].map(([id, list]) => ({
    teamId: id,
    teamName: teamName(id, teams),
    projects: list,
  }));
  teamGroups.sort((a, b) => (a.teamName ?? '').localeCompare(b.teamName ?? ''));

  const groups: ProjectGroup<P>[] = [];
  if (own.length > 0) groups.push({ teamId: null, teamName: null, projects: own });
  return [...groups, ...teamGroups];
}
