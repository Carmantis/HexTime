import { api, query } from './client';
import type { GroupBy, ReportSummary } from './types';

export interface SummaryQuery {
  group_by: GroupBy;
  /** ISO 8601 instants with an offset, half-open: [from, to). */
  from: string;
  to: string;
  /** IANA time zone name, so the backend groups by the user's local days. */
  tz: string;
  /** Only this project's entries; used with group_by 'task'. */
  project_id?: string;
  /**
   * The team report: every member's totals on this team's projects. Totals
   * only, for anyone in the team; never grouped by tag.
   */
  team_id?: string;
}

export function fetchSummary(params: SummaryQuery): Promise<ReportSummary> {
  return api.get<ReportSummary>(`/reports/summary${query({ ...params })}`);
}
