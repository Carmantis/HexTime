<script lang="ts">
  import { Plus } from '@lucide/svelte';

  import { fetchEntries } from '$lib/api/entries';
  import { fetchProjects } from '$lib/api/projects';
  import { fetchSummary } from '$lib/api/reports';
  import type { Project, ReportSummary, TimeEntry } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import EntryForm from '$lib/components/EntryForm.svelte';
  import EntryRow from '$lib/components/EntryRow.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import { dayRange, formatDuration, localTimeZone } from '$lib/format';
  import { locale, t } from '$lib/i18n/index.svelte';
  import { isPlainKey } from '$lib/keyboard';
  import { timer } from '$lib/stores/timer.svelte';

  let entries = $state<TimeEntry[]>([]);
  let projects = $state<Project[]>([]);
  let summary = $state<ReportSummary | null>(null);
  let loading = $state(true);

  let editing = $state<TimeEntry | null>(null);
  let formOpen = $state(false);

  const finished = $derived(entries.filter((entry) => entry.ended_at !== null));

  // The day's total comes from the report service, never from adding up the
  // rows here: views, charts and PDFs must all show the same number.
  const total = $derived(summary?.total_seconds ?? 0);

  function projectOf(entry: TimeEntry): Project | undefined {
    return entry.project_id ? projects.find((p) => p.id === entry.project_id) : undefined;
  }

  async function load(): Promise<void> {
    const { from, to } = dayRange(new Date());
    const [loadedEntries, loadedProjects, loadedSummary] = await Promise.all([
      fetchEntries({ from, to }),
      // Archived projects too: an old entry keeps its colour and name.
      fetchProjects(true),
      fetchSummary({ group_by: 'day', from, to, tz: localTimeZone() }),
    ]);
    entries = loadedEntries;
    projects = loadedProjects;
    summary = loadedSummary;
    loading = false;
  }

  // Reloads whenever the running timer changes, which covers start and stop.
  $effect(() => {
    void timer.running;
    void load().catch(() => (loading = false));
  });

  function openNew(): void {
    editing = null;
    formOpen = true;
  }

  function openEdit(entry: TimeEntry): void {
    editing = entry;
    formOpen = true;
  }

  function close(): void {
    formOpen = false;
    editing = null;
  }

  function saved(): void {
    close();
    void load();
  }

  function onkeydown(event: KeyboardEvent): void {
    if (isPlainKey(event, 'n')) {
      event.preventDefault();
      openNew();
    }
  }
</script>

<svelte:window {onkeydown} />

<section class="view">
  <header class="head">
    <h1>{t('tracking.today')}</h1>
    <div class="right">
      {#if total > 0}
        <span class="total">{formatDuration(total, locale.current)}</span>
      {/if}
      <Button variant="primary" onclick={openNew} title="N">
        <Plus size={16} />
        {t('entry.new')}
      </Button>
    </div>
  </header>

  <div class="card">
    {#if loading}
      <p class="muted">{t('common.loading')}</p>
    {:else if finished.length === 0}
      <EmptyState title={t('tracking.emptyTitle')} body={t('tracking.emptyBody')}>
        {#snippet action()}
          <Button variant="primary" onclick={openNew}>{t('entry.new')}</Button>
        {/snippet}
      </EmptyState>
    {:else}
      <ul class="entries">
        {#each finished as entry (entry.id)}
          <EntryRow {entry} project={projectOf(entry)} onedit={openEdit} />
        {/each}
      </ul>
    {/if}
  </div>
</section>

{#if formOpen}
  <Modal title={editing ? t('entry.edit') : t('entry.new')} onclose={close}>
    <!-- Keyed so the form remounts with fresh state for each entry. -->
    {#key editing?.id ?? 'new'}
      <EntryForm entry={editing} onsaved={saved} oncancel={close} />
    {/key}
  </Modal>
{/if}

<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }

  h1 {
    font-size: var(--text-2xl);
    font-weight: 600;
    color: var(--color-text);
  }

  .right {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .total {
    font-family: var(--font-mono);
    font-size: var(--text-lg);
    color: var(--color-text-muted);
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
