import { api, query, type DownloadedFile } from './client';

export interface PdfQuery {
  /**
   * "period" covers all the user's time; "project" one project, by task;
   * "team" a team's totals per member and project.
   */
  scope: 'period' | 'project' | 'team';
  /** The project's or the team's id. */
  id?: string;
  /** With scope "team": the user's own hours on the team's projects instead. */
  mine?: boolean;
  /** ISO 8601 instants with an offset, half-open: [from, to). */
  from: string;
  to: string;
  /** IANA time zone name, so dates in the PDF are the user's local dates. */
  tz: string;
  /** The UI language; the PDF is written in it. */
  locale: string;
}

export function fetchPdf(params: PdfQuery): Promise<DownloadedFile> {
  return api.download(`/exports/pdf${query({ ...params })}`, 'hextime.pdf');
}
