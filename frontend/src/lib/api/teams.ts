import { api, query } from './client';
import type { MyInvitation, Person, Team, TeamInvitation, TeamMember, TeamRole } from './types';

/** The user's teams; every team for the organisation administrator. */
export function fetchTeams(): Promise<Team[]> {
  return api.get<Team[]>('/teams');
}

/** A new team, with the user as its lead. */
export function createTeam(name: string): Promise<Team> {
  return api.post<Team>('/teams', { name });
}

export function renameTeam(teamId: string, name: string): Promise<Team> {
  return api.patch<Team>(`/teams/${teamId}`, { name });
}

/** Refused (team_has_entries) while hours are booked on its projects. */
export function deleteTeam(teamId: string): Promise<void> {
  return api.remove(`/teams/${teamId}`);
}

export function fetchMembers(teamId: string): Promise<TeamMember[]> {
  return api.get<TeamMember[]>(`/teams/${teamId}/members`);
}

export function changeRole(teamId: string, userId: string, role: TeamRole): Promise<TeamMember> {
  return api.patch<TeamMember>(`/teams/${teamId}/members/${userId}`, { role });
}

/** Remove someone, or leave the team when it is one's own id. */
export function removeMember(teamId: string, userId: string): Promise<void> {
  return api.remove(`/teams/${teamId}/members/${userId}`);
}

/** People in the organisation by name or address, to invite. */
export function findPeople(q: string): Promise<Person[]> {
  return api.get<Person[]>(`/people${query({ q: q || undefined })}`);
}

export function fetchInvitations(teamId: string): Promise<TeamInvitation[]> {
  return api.get<TeamInvitation[]>(`/teams/${teamId}/invitations`);
}

/** Ask someone to join; they answer in the app. */
export function invite(teamId: string, userId: string): Promise<TeamInvitation> {
  return api.post<TeamInvitation>(`/teams/${teamId}/invitations`, { user_id: userId });
}

export function cancelInvitation(teamId: string, userId: string): Promise<void> {
  return api.remove(`/teams/${teamId}/invitations/${userId}`);
}

/** Teams waiting on the signed-in user's answer. */
export function fetchMyInvitations(): Promise<MyInvitation[]> {
  return api.get<MyInvitation[]>('/invitations');
}

export function answerInvitation(teamId: string, accept: boolean): Promise<void> {
  return api.post<void>(`/invitations/${teamId}/${accept ? 'accept' : 'decline'}`);
}
