import { describe, expect, it } from 'vitest';

import type { Team, TeamRole } from '$lib/api/types';
import { canChange, groupProjects, isManager, managedTeams, teamName } from '$lib/teams';

function team(id: string, role: TeamRole | null): Team {
  return {
    id,
    name: `Team ${id}`,
    role,
    member_count: 1,
    can_manage: role === 'lead',
    has_lead: true,
    created_at: '',
  };
}

const TEAMS = [team('a', 'lead'), team('l', 'lead'), team('m', 'member'), team('o', null)];

describe('team roles', () => {
  it('lets leads manage, nobody else', () => {
    expect(['lead', 'member', null].map((r) => isManager(r as TeamRole | null))).toEqual([
      true,
      false,
      false,
    ]);
  });

  it('offers only the teams one manages for new projects', () => {
    expect(managedTeams(TEAMS).map((t) => t.id)).toEqual(['a', 'l']);
  });

  it('allows changing own rows and managed teams’ rows only', () => {
    expect(canChange({ owner_team_id: null }, TEAMS)).toBe(true);
    expect(canChange({ owner_team_id: 'l' }, TEAMS)).toBe(true);
    expect(canChange({ owner_team_id: 'm' }, TEAMS)).toBe(false);
    // An organisation administrator outside the team, or a team not listed.
    expect(canChange({ owner_team_id: 'o' }, TEAMS)).toBe(false);
    expect(canChange({ owner_team_id: 'x' }, TEAMS)).toBe(false);
  });

  it('names the owning team', () => {
    expect(teamName('l', TEAMS)).toBe('Team l');
    expect(teamName(null, TEAMS)).toBeNull();
    expect(teamName('x', TEAMS)).toBeNull();
  });
});

describe('project groups', () => {
  const p = (id: string, owner: string | null) => ({ id, owner_team_id: owner });
  const teams = [team('z', 'member'), team('b', 'lead')];

  it('puts own projects first, then each team by name', () => {
    const groups = groupProjects([p('1', 'z'), p('2', null), p('3', 'b'), p('4', 'z')], teams);

    expect(groups.map((g) => [g.teamName, g.projects.map((x) => x.id)])).toEqual([
      [null, ['2']],
      ['Team b', ['3']],
      ['Team z', ['1', '4']],
    ]);
  });

  it('leaves out empty groups', () => {
    expect(groupProjects([p('1', 'b')], teams).map((g) => g.teamId)).toEqual(['b']);
    expect(groupProjects([], teams)).toEqual([]);
  });

  it('keeps a project whose team is not listed yet', () => {
    const groups = groupProjects([p('1', 'unknown')], teams);

    expect(groups).toEqual([{ teamId: 'unknown', teamName: null, projects: [p('1', 'unknown')] }]);
  });
});
