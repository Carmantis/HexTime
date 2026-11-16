/**
 * Types mirroring the backend's Pydantic schemas.
 *
 * Field names are snake_case because that is what the API sends; translating
 * them would only add a layer that can drift.
 */

export type AppMode = 'local' | 'server';

export interface AppConfig {
  mode: AppMode;
  locales: string[];
  default_locale: string;
  allowed_email_domain: string | null;
  allow_self_registration: boolean;
}

export interface TimeEntry {
  id: string;
  user_id: string;
  project_id: string | null;
  task_id: string | null;
  description: string | null;
  /** ISO 8601, always UTC. Convert to local time only for display. */
  started_at: string;
  ended_at: string | null;
  billable: boolean;
  /** Integer cents, frozen when the entry was created. */
  rate_snapshot_cents: number | null;
  currency: string;
  /** Computed by the backend; null while the timer is still running. */
  duration_seconds: number | null;
  /** A set, not a sequence: the backend returns them sorted by name. */
  tags: Tag[];
}

export interface Project {
  id: string;
  /** Set when the project is a team's; null for the user's own. */
  owner_team_id: string | null;
  name: string;
  color: string;
  client_name: string | null;
  billable_default: boolean;
  hourly_rate_cents: number | null;
  currency: string;
  archived_at: string | null;
}

export interface Task {
  id: string;
  project_id: string;
  name: string;
  archived_at: string | null;
}

export interface Tag {
  id: string;
  /** Set when the tag is a team's; null for the user's own. */
  owner_team_id: string | null;
  name: string;
  color: string;
  archived_at: string | null;
}

export type GroupBy = 'day' | 'month' | 'project' | 'tag' | 'task' | 'user';

export interface ReportGroup {
  /**
   * An ISO date ("2026-03-29") or month ("2026-03"), otherwise a project, tag
   * or task id, or "none" for entries without one.
   */
  key: string;
  total_seconds: number;
  billable_seconds: number;
  billable_amount_cents: number;
  entry_count: number;
}

/**
 * Totals computed by the backend. The frontend only ever displays these —
 * it never adds up durations or money itself.
 */
export interface ReportSummary {
  group_by: GroupBy;
  time_zone: string;
  currency: string;
  groups: ReportGroup[];
  total_seconds: number;
  billable_seconds: number;
  billable_amount_cents: number;
  entry_count: number;
  /** Display names by key, in a by-user summary. */
  labels: Record<string, string>;
}

export interface TimerStartInput {
  project_id?: string | null;
  task_id?: string | null;
  description?: string | null;
  billable?: boolean | null;
  tag_ids?: string[];
}

export interface TimeEntryInput {
  started_at: string;
  ended_at?: string | null;
  project_id?: string | null;
  task_id?: string | null;
  description?: string | null;
  billable?: boolean | null;
  /** Replaces the whole set. Omit to leave the tags untouched. */
  tag_ids?: string[] | null;
}

/** The signed-in user (in local mode, the one desktop user). */
export interface Me {
  id: string;
  email: string | null;
  display_name: string;
  locale: 'fi' | 'en';
  theme: 'dark' | 'light';
  is_admin: boolean;
}

export type TokenPurpose = 'setup' | 'reset' | 'verify';

/** What a link from an email is for, before it is used. */
export interface TokenInfo {
  purpose: TokenPurpose;
  email: string | null;
  display_name: string;
}

export interface MeUpdate {
  display_name?: string;
  locale?: 'fi' | 'en';
  theme?: 'dark' | 'light';
}

export type UserStatus = 'active' | 'invited' | 'unverified' | 'disabled';

/** A row of the administrator's user list. */
export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
  status: UserStatus;
  created_at: string;
}

export type AddOutcome =
  | 'invited'
  | 'resent'
  | 'exists'
  | 'invalid_domain'
  | 'duplicate'
  | 'email_failed';

export interface AddResult {
  email: string;
  display_name: string;
  outcome: AddOutcome;
  user_id: string | null;
}

export type TeamRole = 'member' | 'lead';

export interface Team {
  id: string;
  name: string;
  /** The user's own role; null for an organisation administrator outside it. */
  role: TeamRole | null;
  member_count: number;
  /** May the user run the team: its lead, or the administrator standing in. */
  can_manage: boolean;
  /** False when no lead who can sign in is left. */
  has_lead: boolean;
  created_at: string;
}

export interface TeamMember {
  user_id: string;
  email: string;
  display_name: string;
  role: TeamRole;
  status: UserStatus;
  joined_at: string;
}

/** Someone in the organisation, as the invite search shows them. */
export interface Person {
  id: string;
  email: string;
  display_name: string;
}

/** Someone a team is waiting on. */
export interface TeamInvitation {
  user_id: string;
  email: string;
  display_name: string;
  invited_at: string;
}

/** A team waiting on the signed-in user's answer. */
export interface MyInvitation {
  team_id: string;
  team_name: string;
  invited_by: string | null;
  invited_at: string;
}
