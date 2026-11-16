<script lang="ts">
  import type { Project, TimeEntry } from '$lib/api/types';
  import { formatClock, formatTimeOfDay } from '$lib/format';
  import { locale, t } from '$lib/i18n/index.svelte';

  interface Props {
    entry: TimeEntry;
    project?: Project;
    onedit: (entry: TimeEntry) => void;
  }

  let { entry, project, onedit }: Props = $props();
</script>

<li class="entry" style:--entry-color={project?.color ?? 'transparent'}>
  <button class="open" onclick={() => onedit(entry)} title={t('entry.edit')}>
    <span class="description">{entry.description || t('timer.descriptionPlaceholder')}</span>

    {#if entry.tags.length > 0}
      <span class="tags">
        {#each entry.tags as tag (tag.id)}
          <span class="tag" style:--tag-color={tag.color}>{tag.name}</span>
        {/each}
      </span>
    {/if}

    {#if project}
      <span class="project">{project.name}</span>
    {/if}

    <span class="range">
      {formatTimeOfDay(entry.started_at, locale.current)}–{formatTimeOfDay(
        entry.ended_at ?? entry.started_at,
        locale.current,
      )}
    </span>

    <span class="duration">{formatClock(entry.duration_seconds ?? 0)}</span>
  </button>
</li>

<style>
  /* Project colour as a thin left border, the HexCalendar EventChip pattern. */
  .entry {
    border-left: 3px solid var(--entry-color);
    border-bottom: 1px solid var(--color-border-light);
  }

  .entry:last-child {
    border-bottom: none;
  }

  .open {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-3) var(--space-4);
    border: none;
    background: none;
    text-align: left;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .open:hover {
    background-color: var(--color-surface-hover);
  }

  .open:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -2px;
  }

  .description {
    flex: 1;
    min-width: 0;
    color: var(--color-text);
    font-size: var(--text-sm);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tags {
    display: flex;
    gap: var(--space-1);
    flex-shrink: 0;
  }

  .tag {
    padding: 1px 8px;
    border-radius: var(--radius-xl);
    background-color: color-mix(in srgb, var(--tag-color) 18%, transparent);
    color: var(--color-text);
    font-size: 10px;
    white-space: nowrap;
  }

  .project,
  .range {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    white-space: nowrap;
  }

  .range {
    font-variant-numeric: tabular-nums;
  }

  .duration {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    color: var(--color-text);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
</style>
