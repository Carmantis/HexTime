<script lang="ts">
  import { FileDown } from '@lucide/svelte';
  import type { EChartsCoreOption } from 'echarts/core';

  import { ApiError } from '$lib/api/client';
  import { fetchPdf } from '$lib/api/exports';
  import { fetchProjects, fetchTasks } from '$lib/api/projects';
  import { fetchSummary } from '$lib/api/reports';
  import { fetchTags } from '$lib/api/tags';
  import type { Project, ReportSummary, Tag, Task } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import Chart from '$lib/components/Chart.svelte';
  import DateRangeNav from '$lib/components/DateRangeNav.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import { chartTokens, hourAxis, hoursLabel } from '$lib/chart';
  import {
    formatDuration,
    isoWeek,
    localTimeZone,
    rangeOf,
    shiftRange,
    type RangeMode,
  } from '$lib/format';
  import { locale, t } from '$lib/i18n/index.svelte';
  import { saveFile } from '$lib/download';
  import { isPlainKey } from '$lib/keyboard';
  import { formatCents } from '$lib/money';
  import { SWATCHES } from '$lib/palette';
  import { appConfig } from '$lib/stores/config.svelte';
  import { picker, refreshPicker } from '$lib/stores/picker.svelte';
  import { theme } from '$lib/stores/theme.svelte';

  const MODES: RangeMode[] = ['week', 'month', 'year'];

  let mode = $state<RangeMode>('month');
  let anchor = $state(new Date());

  let byProject = $state<ReportSummary | null>(null);
  let byTag = $state<ReportSummary | null>(null);
  let byPeriod = $state<ReportSummary | null>(null);
  /** Team scope only: each member's totals on the team's projects. */
  let byMember = $state<ReportSummary | null>(null);

  /**
   * Whose hours: '' for one's own, or a team's id for the team report —
   * every member's totals on the team's projects, never single entries.
   */
  let teamId = $state('');
  /** Teams the user is in. (An administrator outside a team sees no hours.) */
  const myTeams = $derived(picker.teams.filter((team) => team.role !== null));
  let projects = $state<Project[]>([]);
  let tags = $state<Tag[]>([]);
  let loading = $state(true);
  /** Why the numbers could not be loaded; the old ones are not shown then. */
  let loadError = $state<string | null>(null);

  // Hours by task, for one project at a time: task names only mean something
  // inside their own project.
  let taskProjectId = $state('');
  let byTask = $state<ReportSummary | null>(null);
  let tasks = $state<Task[]>([]);

  /** Which PDF is being made, so only that button waits. */
  type Export = 'period' | 'project' | 'team' | 'mine';
  let exporting = $state<Export | null>(null);
  let exportError = $state<string | null>(null);

  /**
   * Fetch the PDF for what is on screen and hand it to the browser.
   *
   * The backend builds it from the same reports service as this view, in the
   * UI's language and the browser's time zone, so the numbers match.
   */
  async function exportPdf(which: Export): Promise<void> {
    exporting = which;
    exportError = null;
    const inTeam = which === 'team' || which === 'mine';
    try {
      const file = await fetchPdf({
        scope: inTeam ? 'team' : which,
        id: inTeam ? teamId : which === 'project' ? taskProjectId : undefined,
        mine: which === 'mine' || undefined,
        from: range.start.toISOString(),
        to: range.end.toISOString(),
        tz: localTimeZone(),
        locale: locale.current,
      });
      await saveFile(file);
    } catch (error) {
      exportError = error instanceof ApiError ? error.code : 'unknown_error';
    } finally {
      exporting = null;
    }
  }

  const range = $derived(rangeOf(anchor, mode));
  /** A year is charted month by month, anything shorter day by day. */
  const periodGroup = $derived(mode === 'year' ? 'month' : 'day');

  const label = $derived.by(() => {
    const formats: Record<RangeMode, Intl.DateTimeFormatOptions> = {
      day: { dateStyle: 'full' },
      week: { day: 'numeric', month: 'numeric', year: 'numeric' },
      month: { month: 'long', year: 'numeric' },
      year: { year: 'numeric' },
    };
    if (mode === 'week') {
      return `${t('calendar.weekNumber', { n: isoWeek(range.start) })} · ${new Intl.DateTimeFormat(
        locale.current,
        formats.week,
      ).formatRange(range.start, new Date(range.end.getTime() - 1))}`;
    }
    return new Intl.DateTimeFormat(locale.current, formats[mode]).format(range.start);
  });

  let latest = 0;

  async function load(): Promise<void> {
    const request = ++latest;
    const from = range.start.toISOString();
    const to = range.end.toISOString();
    const tz = localTimeZone();
    const team = teamId || undefined;
    const base = { from, to, tz, team_id: team };
    if (loadError) {
      // Not the old error under a new heading while the new numbers load.
      loadError = null;
      loading = true;
    }

    try {
      const [project, tag, period, member, loadedProjects, loadedTags] = await Promise.all([
        fetchSummary({ group_by: 'project', ...base }),
        // Tags are personal: a team report is never grouped by them.
        team ? null : fetchSummary({ group_by: 'tag', ...base }),
        fetchSummary({ group_by: periodGroup, ...base }),
        team ? fetchSummary({ group_by: 'user', ...base }) : null,
        // Archived ones too, so an old entry's project still has a name.
        fetchProjects(true),
        fetchTags(true),
      ]);
      if (request !== latest) return;

      byProject = project;
      byTag = tag;
      byPeriod = period;
      byMember = member;
      projects = loadedProjects;
      tags = loadedTags;
    } catch (error) {
      if (request !== latest) return;
      // No old numbers under a new heading: they would be for another range or team.
      loadError = error instanceof ApiError ? error.code : 'unknown_error';
      byProject = byTag = byPeriod = byMember = byTask = null;
      tasks = [];
      // Perhaps the user is no longer in the team: a fresh list of teams lets
      // the effect below fall back to their own hours.
      if (team) void refreshPicker();
    }
    loading = false;
  }

  $effect(() => {
    void range;
    void periodGroup;
    void teamId;
    void load();
  });

  // A team the user has left (or that was deleted) drops out of the picker;
  // fall back to one's own hours instead of asking for it again and again.
  $effect(() => {
    if (teamId && !myTeams.some((team) => team.id === teamId)) teamId = '';
  });

  // The teams to choose from (server mode only).
  $effect(() => {
    if (appConfig.isServer) void refreshPicker();
  });

  /** Projects with time in this period, busiest first — the task picker's options. */
  const projectsWithTime = $derived(
    (byProject?.groups ?? []).filter((group) => group.key !== 'none' && group.total_seconds > 0),
  );

  // Keep the picked project while it still has time in the new period;
  // otherwise fall back to the busiest one.
  $effect(() => {
    const keys = projectsWithTime.map((group) => group.key);
    if (!keys.includes(taskProjectId)) taskProjectId = keys[0] ?? '';
  });

  let latestTasks = 0;

  async function loadTasks(projectId: string): Promise<void> {
    const request = ++latestTasks;
    // In the team report a project is split by member, not by task.
    const team = teamId || undefined;
    const [summary, loadedTasks] = await Promise.all([
      fetchSummary({
        group_by: team ? 'user' : 'task',
        from: range.start.toISOString(),
        to: range.end.toISOString(),
        tz: localTimeZone(),
        project_id: projectId,
        team_id: team,
      }),
      fetchTasks(projectId, true),
    ]);
    if (request !== latestTasks) return;

    byTask = summary;
    tasks = loadedTasks;
  }

  $effect(() => {
    void teamId;
    if (!taskProjectId) {
      byTask = null;
      return;
    }
    void loadTasks(taskProjectId).catch(() => (byTask = null));
  });

  function projectName(key: string): string {
    if (key === 'none') return t('reports.noProject');
    return projects.find((p) => p.id === key)?.name ?? t('reports.deletedProject');
  }

  function projectColor(key: string, fallback: string): string {
    return projects.find((p) => p.id === key)?.color ?? fallback;
  }

  function tagName(key: string): string {
    if (key === 'none') return t('reports.noTag');
    return tags.find((g) => g.id === key)?.name ?? t('reports.deletedTag');
  }

  function tagColor(key: string, fallback: string): string {
    return tags.find((g) => g.id === key)?.color ?? fallback;
  }

  function taskName(key: string): string {
    if (key === 'none') return t('reports.noTask');
    return tasks.find((task) => task.id === key)?.name ?? t('reports.deletedTask');
  }

  /** A member's name from the summary that has them, people who left too. */
  function memberName(summary: ReportSummary): (key: string) => string {
    return (key) => summary.labels[key] ?? t('reports.unknownMember');
  }

  /** Tasks have no colour of their own; the bars take the palette in order. */
  function taskColor(_key: string, fallback: string): string {
    return fallback;
  }

  /** A period key ("2026-05-04" or "2026-05") as a short axis label. */
  function periodLabel(key: string): string {
    const parts = key.split('-').map(Number);
    if (parts.length === 2) {
      return new Intl.DateTimeFormat(locale.current, { month: 'short' }).format(
        new Date(parts[0], parts[1] - 1, 1),
      );
    }
    return new Intl.DateTimeFormat(locale.current, { day: 'numeric', month: 'numeric' }).format(
      new Date(parts[0], parts[1] - 1, parts[2]),
    );
  }

  /**
   * A horizontal bar per group, biggest at the top, each in its own colour.
   *
   * Reading `theme.current` here is what makes the chart follow a theme
   * switch: the option is rebuilt, and Chart re-applies it.
   */
  function barsOption(
    summary: ReportSummary,
    name: (key: string) => string,
    color: (key: string, fallback: string) => string,
  ): EChartsCoreOption {
    void theme.current;
    const tokens = chartTokens();
    const rows = summary.groups.filter((group) => group.total_seconds > 0);
    // Headroom past the longest bar keeps its "16 h 30 min" label inside the card.
    const axis = hourAxis(Math.max(0, ...rows.map((group) => group.total_seconds)) * 1.25, 4);

    return {
      grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'item',
        backgroundColor: tokens.surface,
        borderColor: tokens.border,
        textStyle: { color: tokens.text },
        formatter: (params: { name: string; value: number }) =>
          `${params.name}: ${hoursLabel(params.value, locale.current)}`,
      },
      xAxis: {
        type: 'value',
        ...axis,
        axisLabel: {
          color: tokens.muted,
          formatter: (value: number) => hoursLabel(value, locale.current),
        },
        splitLine: { lineStyle: { color: tokens.border } },
      },
      // Reversed: ECharts draws a category axis bottom-up, and the biggest
      // group should sit at the top.
      yAxis: {
        type: 'category',
        data: rows.map((group) => name(group.key)).reverse(),
        axisLabel: { color: tokens.text },
        axisLine: { lineStyle: { color: tokens.border } },
      },
      series: [
        {
          type: 'bar',
          data: rows
            .map((group, index) => ({
              value: group.total_seconds,
              itemStyle: {
                color: color(group.key, SWATCHES[index % SWATCHES.length]),
                borderRadius: [0, 4, 4, 0],
              },
            }))
            .reverse(),
          barMaxWidth: 22,
          label: {
            show: true,
            position: 'right',
            color: tokens.muted,
            formatter: (params: { value: number }) => hoursLabel(params.value, locale.current),
          },
        },
      ],
    };
  }

  /** One bar per day or month, in chronological order. */
  function periodOption(summary: ReportSummary): EChartsCoreOption {
    void theme.current;
    const tokens = chartTokens();
    const axis = hourAxis(Math.max(0, ...summary.groups.map((group) => group.total_seconds)), 5);

    return {
      grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: tokens.surface,
        borderColor: tokens.border,
        textStyle: { color: tokens.text },
        formatter: (params: { name: string; value: number }[]) =>
          `${params[0].name}: ${hoursLabel(params[0].value, locale.current)}`,
      },
      xAxis: {
        type: 'category',
        data: summary.groups.map((group) => periodLabel(group.key)),
        axisLabel: { color: tokens.muted, interval: 'auto' },
        axisLine: { lineStyle: { color: tokens.border } },
      },
      yAxis: {
        type: 'value',
        ...axis,
        axisLabel: {
          color: tokens.muted,
          formatter: (value: number) => hoursLabel(value, locale.current),
        },
        splitLine: { lineStyle: { color: tokens.border } },
      },
      series: [
        {
          type: 'bar',
          data: summary.groups.map((group) => group.total_seconds),
          itemStyle: { color: tokens.accent, borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 28,
        },
      ],
    };
  }

  const hasData = $derived((byProject?.total_seconds ?? 0) > 0);

  function onkeydown(event: KeyboardEvent): void {
    if (isPlainKey(event, 'ArrowLeft')) {
      event.preventDefault();
      anchor = shiftRange(anchor, mode, -1);
    } else if (isPlainKey(event, 'ArrowRight')) {
      event.preventDefault();
      anchor = shiftRange(anchor, mode, 1);
    } else if (isPlainKey(event, 't')) {
      event.preventDefault();
      anchor = new Date();
    }
  }
</script>

<svelte:window {onkeydown} />

<section class="view">
  <header class="head">
    <div class="range-nav">
      <DateRangeNav
        {mode}
        {label}
        modes={MODES}
        onprev={() => (anchor = shiftRange(anchor, mode, -1))}
        onnext={() => (anchor = shiftRange(anchor, mode, 1))}
        ontoday={() => (anchor = new Date())}
        onmode={(next) => (mode = next)}
      />
    </div>
    <div class="actions">
      {#if myTeams.length > 0}
        <label>
          <span class="sr-only">{t('reports.scope')}</span>
          <select bind:value={teamId}>
            <option value="">{t('reports.myHours')}</option>
            {#each myTeams as team (team.id)}
              <option value={team.id}>{t('reports.teamScope', { name: team.name })}</option>
            {/each}
          </select>
        </label>
      {/if}
      {#if teamId}
        <Button
          onclick={() => exportPdf('team')}
          disabled={!hasData || exporting !== null}
          title={t('reports.exportTeamPdfHint')}
        >
          <FileDown size={16} />
          {exporting === 'team' ? t('reports.exporting') : t('reports.exportTeamPdf')}
        </Button>
        <Button
          variant="ghost"
          onclick={() => exportPdf('mine')}
          disabled={!hasData || exporting !== null}
          title={t('reports.exportMinePdfHint')}
        >
          <FileDown size={16} />
          {exporting === 'mine' ? t('reports.exporting') : t('reports.exportMinePdf')}
        </Button>
      {:else}
        <Button
          onclick={() => exportPdf('period')}
          disabled={!hasData || exporting !== null}
          title={t('reports.exportPdfHint')}
        >
          <FileDown size={16} />
          {exporting === 'period' ? t('reports.exporting') : t('reports.exportPdf')}
        </Button>
      {/if}
    </div>
  </header>

  {#if teamId}
    <p class="note">{t('reports.teamNote')}</p>
  {/if}

  {#if loadError}
    <p class="error" role="alert">{t(`errors.${loadError}`)}</p>
  {/if}
  {#if exportError}
    <p class="error" role="alert">{t(`errors.${exportError}`)}</p>
  {/if}

  {#if loading}
    <div class="card"><p class="muted">{t('common.loading')}</p></div>
  {:else if loadError}
    <!-- The error above says what went wrong; "no hours" would not be true. -->
    <div class="card">
      <Button variant="secondary" onclick={() => void load()}>{t('common.retry')}</Button>
    </div>
  {:else if !hasData}
    <div class="card">
      <EmptyState
        title={t('reports.emptyTitle')}
        body={teamId ? t('reports.teamEmptyBody') : t('reports.emptyBody')}
      />
    </div>
  {:else}
    <div class="totals">
      <div class="tile">
        <span class="tile-label">{t('reports.totalHours')}</span>
        <span class="tile-value">
          {formatDuration(byProject?.total_seconds ?? 0, locale.current)}
        </span>
      </div>
      <div class="tile">
        <span class="tile-label">{t('reports.billableHours')}</span>
        <span class="tile-value">
          {formatDuration(byProject?.billable_seconds ?? 0, locale.current)}
        </span>
      </div>
      <div class="tile">
        <span class="tile-label">{t('reports.billableAmount')}</span>
        <span class="tile-value accent">
          {formatCents(
            byProject?.billable_amount_cents ?? 0,
            locale.current,
            byProject?.currency ?? 'EUR',
          )}
        </span>
      </div>
    </div>

    {#if byPeriod}
      <section class="card">
        <h2>{mode === 'year' ? t('reports.perMonth') : t('reports.perDay')}</h2>
        <Chart
          option={periodOption(byPeriod)}
          height={220}
          ariaLabel={mode === 'year' ? t('reports.perMonth') : t('reports.perDay')}
        />
      </section>
    {/if}

    <div class="side-by-side">
      {#if byMember}
        <section class="card">
          <h2>{t('reports.byMember')}</h2>
          <Chart
            option={barsOption(byMember, memberName(byMember), taskColor)}
            height={Math.max(160, byMember.groups.filter((g) => g.total_seconds > 0).length * 38)}
            ariaLabel={t('reports.byMember')}
          />
        </section>
      {/if}

      {#if byProject}
        <section class="card">
          <h2>{t('reports.byProject')}</h2>
          <Chart
            option={barsOption(byProject, projectName, projectColor)}
            height={Math.max(160, byProject.groups.filter((g) => g.total_seconds > 0).length * 38)}
            ariaLabel={t('reports.byProject')}
          />
        </section>
      {/if}

      {#if byTag}
        <section class="card">
          <h2>{t('reports.byTag')}</h2>
          {#if byTag.groups.some((g) => g.total_seconds > 0)}
            <Chart
              option={barsOption(byTag, tagName, tagColor)}
              height={Math.max(160, byTag.groups.filter((g) => g.total_seconds > 0).length * 38)}
              ariaLabel={t('reports.byTag')}
            />
            <p class="note">{t('reports.tagNote')}</p>
          {/if}
        </section>
      {/if}
    </div>

    {#if projectsWithTime.length > 0}
      <section class="card">
        <div class="card-head">
          <h2>{teamId ? t('reports.membersByProject') : t('reports.byTask')}</h2>
          <label>
            <span class="sr-only">{t('reports.taskProject')}</span>
            <select bind:value={taskProjectId}>
              {#each projectsWithTime as group (group.key)}
                <option value={group.key}>{projectName(group.key)}</option>
              {/each}
            </select>
          </label>
          <Button
            variant="ghost"
            onclick={() => exportPdf('project')}
            disabled={!taskProjectId || exporting !== null}
            title={t('reports.exportProjectPdfHint')}
          >
            <FileDown size={16} />
            {exporting === 'project'
              ? t('reports.exporting')
              : teamId
                ? t('reports.exportMyProjectPdf')
                : t('reports.exportProjectPdf')}
          </Button>
        </div>
        {#if byTask}
          <Chart
            option={barsOption(byTask, teamId ? memberName(byTask) : taskName, taskColor)}
            height={Math.max(120, byTask.groups.filter((g) => g.total_seconds > 0).length * 38)}
            ariaLabel={t('reports.byTask')}
          />
        {/if}
      </section>
    {/if}
  {/if}
</section>

<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5);
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3) var(--space-4);
  }

  /* Wide enough for the period's name; the actions wrap below it before
     the name would be cut short. */
  .range-nav {
    display: flex;
    flex: 1 1 560px;
    min-width: 0;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }

  .error {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
    color: var(--color-error);
    font-size: var(--text-sm);
  }

  .totals {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--space-4);
  }

  .tile {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-4);
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .tile-label {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
  }

  .tile-value {
    font-family: var(--font-mono);
    font-size: var(--text-xl);
    color: var(--color-text);
    font-variant-numeric: tabular-nums;
  }

  .accent {
    color: var(--color-accent);
  }

  .side-by-side {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: var(--space-4);
    align-items: start;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4);
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .card-head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  /* The title takes the free space; the picker and the button sit right. */
  .card-head h2 {
    margin-right: auto;
  }

  select {
    padding: 5px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
    cursor: pointer;
  }

  select:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  h2 {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--color-text);
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .note {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    line-height: 1.5;
  }
</style>
