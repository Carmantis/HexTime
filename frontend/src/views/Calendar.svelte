<script lang="ts">
  import { Plus } from '@lucide/svelte';

  import { fetchEntries } from '$lib/api/entries';
  import { fetchProjects } from '$lib/api/projects';
  import { fetchSummary } from '$lib/api/reports';
  import type { Project, ReportGroup, ReportSummary, TimeEntry } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import DateRangeNav from '$lib/components/DateRangeNav.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import EntryForm from '$lib/components/EntryForm.svelte';
  import EntryRow from '$lib/components/EntryRow.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import {
    addDays,
    daysIn,
    formatDuration,
    formatTimeOfDay,
    isoWeek,
    localDateKey,
    localMonthKey,
    localTimeZone,
    monthWeeks,
    rangeOf,
    shiftRange,
    type RangeMode,
  } from '$lib/format';
  import { locale, t } from '$lib/i18n/index.svelte';
  import { isPlainKey } from '$lib/keyboard';
  import { formatCents } from '$lib/money';
  import { timer } from '$lib/stores/timer.svelte';

  let mode = $state<RangeMode>('week');
  let anchor = $state(new Date());

  let entries = $state<TimeEntry[]>([]);
  let projects = $state<Project[]>([]);
  let summary = $state<ReportSummary | null>(null);
  let loading = $state(true);

  // `undefined` = closed, `null` = creating, an entry = editing it.
  let dialog = $state<TimeEntry | null | undefined>(undefined);
  let dialogDay = $state<string | undefined>(undefined);

  const range = $derived(rangeOf(anchor, mode));
  const days = $derived(daysIn(range.start, range.end));
  const weeks = $derived(mode === 'month' ? monthWeeks(range.start) : []);
  const months = $derived(
    mode === 'year'
      ? Array.from({ length: 12 }, (_, index) => new Date(range.start.getFullYear(), index, 1))
      : [],
  );
  const thisMonthKey = localMonthKey(new Date());
  const todayKey = localDateKey(new Date());

  const finished = $derived(entries.filter((entry) => entry.ended_at !== null));

  /** Entries per local day, oldest first. Grouping only — no arithmetic. */
  const byDay = $derived.by(() => {
    const map = new Map<string, TimeEntry[]>();
    for (const entry of finished) {
      const key = localDateKey(new Date(entry.started_at));
      map.set(key, [...(map.get(key) ?? []), entry]);
    }
    for (const list of map.values()) {
      list.sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at));
    }
    return map;
  });

  const label = $derived.by(() => {
    if (mode === 'year') return String(range.start.getFullYear());
    if (mode === 'month') {
      return new Intl.DateTimeFormat(locale.current, { month: 'long', year: 'numeric' }).format(
        range.start,
      );
    }
    if (mode === 'day') {
      return new Intl.DateTimeFormat(locale.current, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }).format(range.start);
    }
    const span = new Intl.DateTimeFormat(locale.current, {
      day: 'numeric',
      month: 'numeric',
      year: 'numeric',
    }).formatRange(range.start, addDays(range.start, 6));
    return `${t('calendar.weekNumber', { n: isoWeek(range.start) })} · ${span}`;
  });

  /** The backend's group for one local day ("2026-03-29") or month ("2026-03"). */
  function groupOf(key: string): ReportGroup | undefined {
    return summary?.groups.find((group) => group.key === key);
  }

  function dayTotal(key: string): number {
    return groupOf(key)?.total_seconds ?? 0;
  }

  /**
   * How full a month's bar is, relative to the busiest month of the year.
   * Only scales the backend's numbers for drawing; nothing is summed here.
   */
  const busiestMonth = $derived(
    mode === 'year' ? Math.max(0, ...(summary?.groups ?? []).map((g) => g.total_seconds)) : 0,
  );

  function projectOf(entry: TimeEntry): Project | undefined {
    return entry.project_id ? projects.find((p) => p.id === entry.project_id) : undefined;
  }

  function weekday(day: Date): string {
    return new Intl.DateTimeFormat(locale.current, { weekday: 'short' }).format(day);
  }

  // Answers can arrive out of order when the user clicks through weeks
  // quickly; only the newest request is allowed to write the state.
  let latest = 0;

  async function load(): Promise<void> {
    const request = ++latest;
    const from = range.start.toISOString();
    const to = range.end.toISOString();

    // The month and year grids show only totals, so they skip the entry list
    // instead of downloading a whole year of entries.
    const listsEntries = mode === 'day' || mode === 'week';
    const [loadedEntries, loadedProjects, loadedSummary] = await Promise.all([
      listsEntries ? fetchEntries({ from, to }) : Promise.resolve([]),
      // Archived projects too: an old entry keeps its colour and name.
      fetchProjects(true),
      fetchSummary({
        group_by: mode === 'year' ? 'month' : 'day',
        from,
        to,
        tz: localTimeZone(),
      }),
    ]);
    if (request !== latest) return;

    entries = loadedEntries;
    projects = loadedProjects;
    summary = loadedSummary;
    loading = false;
  }

  $effect(() => {
    void range;
    void timer.running;
    void load().catch(() => (loading = false));
  });

  function step(direction: -1 | 1): void {
    anchor = shiftRange(anchor, mode, direction);
  }

  function openDay(day: Date): void {
    anchor = day;
    mode = 'day';
  }

  function openWeek(monday: Date): void {
    anchor = monday;
    mode = 'week';
  }

  function openMonth(first: Date): void {
    anchor = first;
    mode = 'month';
  }

  function inMonth(day: Date): boolean {
    return day >= range.start && day < range.end;
  }

  /** New entries go on today if it is on screen, else on the first day shown. */
  function defaultDay(): string {
    const keys = days.map(localDateKey);
    return keys.includes(todayKey) ? todayKey : keys[0];
  }

  function openNew(): void {
    dialogDay = defaultDay();
    dialog = null;
  }

  function openEdit(entry: TimeEntry): void {
    dialogDay = undefined;
    dialog = entry;
  }

  function close(): void {
    dialog = undefined;
  }

  function saved(): void {
    close();
    void load();
  }

  function onkeydown(event: KeyboardEvent): void {
    if (isPlainKey(event, 'ArrowLeft')) {
      event.preventDefault();
      step(-1);
    } else if (isPlainKey(event, 'ArrowRight')) {
      event.preventDefault();
      step(1);
    } else if (isPlainKey(event, 't')) {
      event.preventDefault();
      anchor = new Date();
    } else if (isPlainKey(event, 'n')) {
      event.preventDefault();
      openNew();
    }
  }
</script>

<svelte:window {onkeydown} />

<section class="view">
  <header class="head">
    <DateRangeNav
      {mode}
      {label}
      modes={['day', 'week', 'month', 'year']}
      onprev={() => step(-1)}
      onnext={() => step(1)}
      ontoday={() => (anchor = new Date())}
      onmode={(next) => (mode = next)}
    />

    <div class="right">
      {#if summary && summary.total_seconds > 0}
        <span class="total">{formatDuration(summary.total_seconds, locale.current)}</span>
        {#if summary.billable_amount_cents > 0}
          <span class="amount">
            {formatCents(summary.billable_amount_cents, locale.current, summary.currency)}
          </span>
        {/if}
      {/if}
      <Button variant="primary" onclick={openNew} title="N">
        <Plus size={16} />
        {t('entry.new')}
      </Button>
    </div>
  </header>

  {#if mode === 'year'}
    <div class="year">
      {#each months as first (first.getTime())}
        {@const key = localMonthKey(first)}
        {@const group = groupOf(key)}
        {@const name = new Intl.DateTimeFormat(locale.current, { month: 'long' }).format(first)}
        <button
          class="month-card"
          class:today={key === thisMonthKey}
          onclick={() => openMonth(first)}
          aria-label={t('calendar.openMonth', {
            month: new Intl.DateTimeFormat(locale.current, {
              month: 'long',
              year: 'numeric',
            }).format(first),
          })}
        >
          <span class="month-name">{name}</span>
          <span class="month-total" class:empty={!group?.total_seconds}>
            {group?.total_seconds ? formatDuration(group.total_seconds, locale.current) : '–'}
          </span>
          <span class="month-amount">
            {#if summary && group && group.billable_amount_cents > 0}
              {formatCents(group.billable_amount_cents, locale.current, summary.currency)}
            {/if}
          </span>
          <span class="bar" aria-hidden="true">
            <span
              class="bar-fill"
              style:width={busiestMonth > 0
                ? `${((group?.total_seconds ?? 0) / busiestMonth) * 100}%`
                : '0%'}
            ></span>
          </span>
        </button>
      {/each}
    </div>
  {:else if mode === 'month'}
    <div class="month">
      <div class="month-row month-head" aria-hidden="true">
        <span class="week-no"></span>
        {#each daysIn(weeks[0], addDays(weeks[0], 7)) as day (day.getTime())}
          <span class="weekday">{weekday(day)}</span>
        {/each}
      </div>

      {#each weeks as monday (monday.getTime())}
        {@const number = isoWeek(monday)}
        <div class="month-row">
          <button
            class="week-no"
            onclick={() => openWeek(monday)}
            aria-label={t('calendar.openWeek', { n: number })}
          >
            {number}
          </button>

          {#each daysIn(monday, addDays(monday, 7)) as day (day.getTime())}
            {@const key = localDateKey(day)}
            <!-- Days of the neighbouring months only fill the grid: the summary
                 covers this month, so they show no total. -->
            <button
              class="cell"
              class:today={key === todayKey}
              class:outside={!inMonth(day)}
              onclick={() => openDay(day)}
              aria-label={t('calendar.openDay', {
                date: new Intl.DateTimeFormat(locale.current, { dateStyle: 'full' }).format(day),
              })}
            >
              <span class="date">{day.getDate()}</span>
              {#if inMonth(day) && dayTotal(key) > 0}
                <span class="cell-total">{formatDuration(dayTotal(key), locale.current)}</span>
              {/if}
            </button>
          {/each}
        </div>
      {/each}
    </div>
  {:else if mode === 'week'}
    <div class="week">
      {#each days as day (day.getTime())}
        {@const key = localDateKey(day)}
        <div class="column" class:today={key === todayKey}>
          <button
            class="day-head"
            onclick={() => openDay(day)}
            aria-label={t('calendar.openDay', {
              date: new Intl.DateTimeFormat(locale.current, { dateStyle: 'full' }).format(day),
            })}
          >
            <span class="weekday">{weekday(day)}</span>
            <span class="date">{day.getDate()}</span>
          </button>

          <ul class="chips">
            {#each byDay.get(key) ?? [] as entry (entry.id)}
              {@const project = projectOf(entry)}
              <li>
                <!-- HexCalendar's EventChip: colour as a thin border and a light tint. -->
                <button
                  class="chip"
                  style:--chip-color={project?.color ?? 'var(--color-border)'}
                  onclick={() => openEdit(entry)}
                  title={entry.description ?? project?.name ?? ''}
                >
                  <span class="time">{formatTimeOfDay(entry.started_at, locale.current)}</span>
                  <span class="title">
                    {entry.description || project?.name || t('timer.descriptionPlaceholder')}
                  </span>
                </button>
              </li>
            {/each}
          </ul>

          <footer class="day-total">
            {dayTotal(key) > 0 ? formatDuration(dayTotal(key), locale.current) : ''}
          </footer>
        </div>
      {/each}
    </div>
  {:else}
    <div class="card">
      {#if loading}
        <p class="muted">{t('common.loading')}</p>
      {:else if finished.length === 0}
        <EmptyState title={t('calendar.emptyTitle')} body={t('calendar.emptyBody')}>
          {#snippet action()}
            <Button variant="primary" onclick={openNew}>{t('entry.new')}</Button>
          {/snippet}
        </EmptyState>
      {:else}
        <ul class="entries">
          {#each byDay.get(localDateKey(range.start)) ?? [] as entry (entry.id)}
            <EntryRow {entry} project={projectOf(entry)} onedit={openEdit} />
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</section>

{#if dialog !== undefined}
  <Modal title={dialog ? t('entry.edit') : t('entry.new')} onclose={close}>
    {#key dialog?.id ?? `new-${dialogDay}`}
      <EntryForm entry={dialog} day={dialogDay} onsaved={saved} oncancel={close} />
    {/key}
  </Modal>
{/if}

<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5);
    height: 100%;
  }

  .head {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .right {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    flex-shrink: 0;
  }

  .total,
  .amount {
    font-family: var(--font-mono);
    font-size: var(--text-base);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .amount {
    color: var(--color-text);
  }

  .week {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    flex: 1;
    min-height: 0;
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .column {
    display: flex;
    flex-direction: column;
    min-width: 0;
    border-right: 1px solid var(--color-border-light);
  }

  .column:last-child {
    border-right: none;
  }

  /* The same 8 % accent tint HexCalendar gives today's cell. */
  .column.today {
    background-color: color-mix(in srgb, var(--color-accent) 8%, transparent);
  }

  .day-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border: none;
    border-bottom: 1px solid var(--color-border);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    text-transform: capitalize;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .day-head:hover {
    background-color: var(--color-surface-hover);
  }

  .day-head:focus-visible,
  .chip:focus-visible,
  .month-card:focus-visible,
  .cell:focus-visible,
  .week-no:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -2px;
  }

  .date {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: 500;
  }

  .today .date {
    background-color: var(--color-accent);
    color: var(--color-on-accent);
    font-weight: 700;
  }

  .chips {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    padding: var(--space-1);
    list-style: none;
    overflow-y: auto;
  }

  .chip {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    width: 100%;
    padding: 2px 6px;
    border: none;
    border-left: 3px solid var(--chip-color);
    border-radius: var(--radius-sm);
    background-color: color-mix(in srgb, var(--chip-color) 20%, transparent);
    font-size: var(--text-xs);
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    cursor: pointer;
    transition: opacity 0.15s ease;
  }

  .chip:hover {
    opacity: 0.85;
  }

  .time {
    flex-shrink: 0;
    color: var(--color-text-muted);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .title {
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--color-text);
  }

  .day-total {
    min-height: 28px;
    padding: var(--space-1) var(--space-3);
    border-top: 1px solid var(--color-border-light);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    text-align: right;
  }

  .month {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  /* A narrow ISO week number column, then Monday to Sunday. */
  .month-row {
    display: grid;
    grid-template-columns: 40px repeat(7, minmax(0, 1fr));
    flex: 1;
    min-height: 0;
    border-bottom: 1px solid var(--color-border-light);
  }

  .month-row:last-child {
    border-bottom: none;
  }

  .month-head {
    flex: none;
    border-bottom: 1px solid var(--color-border);
  }

  .month-head .weekday {
    padding: var(--space-2) var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    text-transform: capitalize;
  }

  .week-no {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: var(--space-2) 0;
    border: none;
    border-right: 1px solid var(--color-border-light);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-variant-numeric: tabular-nums;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .month-head .week-no {
    cursor: default;
  }

  .cell {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: space-between;
    min-width: 0;
    padding: var(--space-1) var(--space-2);
    border: none;
    border-right: 1px solid var(--color-border-light);
    background: none;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .cell:last-child {
    border-right: none;
  }

  .cell:hover,
  .month-row:not(.month-head) .week-no:hover {
    background-color: var(--color-surface-hover);
  }

  .cell.today {
    background-color: color-mix(in srgb, var(--color-accent) 8%, transparent);
  }

  .cell.outside .date {
    color: var(--color-text-muted);
  }

  .cell-total {
    align-self: flex-end;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .year {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-3);
  }

  @media (max-width: 1000px) {
    .year {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  .month-card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background-color: var(--color-surface);
    color: var(--color-text);
    text-align: left;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .month-card:hover {
    background-color: var(--color-surface-hover);
  }

  .month-card.today {
    background-color: color-mix(in srgb, var(--color-accent) 8%, var(--color-surface));
    border-color: var(--color-accent);
  }

  .month-name {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    text-transform: capitalize;
  }

  .month-total {
    font-family: var(--font-mono);
    font-size: var(--text-xl);
    font-variant-numeric: tabular-nums;
  }

  .month-total.empty {
    color: var(--color-text-muted);
  }

  .month-amount {
    min-height: 1.2em;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
  }

  .bar {
    width: 100%;
    height: 4px;
    margin-top: var(--space-2);
    border-radius: 2px;
    background-color: var(--color-border-light);
    overflow: hidden;
  }

  .bar-fill {
    display: block;
    height: 100%;
    background-color: var(--color-accent);
  }

  .card {
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .muted {
    padding: var(--space-5);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .entries {
    list-style: none;
  }
</style>
