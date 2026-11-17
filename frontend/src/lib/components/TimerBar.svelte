<script lang="ts">
  import { Play, Square, Tag as TagIcon, Users } from '@lucide/svelte';

  import { fetchTasks } from '$lib/api/projects';
  import type { Task } from '$lib/api/types';
  import ProjectOptions from '$lib/components/ProjectOptions.svelte';
  import TagPicker from '$lib/components/TagPicker.svelte';
  import { formatClock } from '$lib/format';
  import { t } from '$lib/i18n/index.svelte';
  import { appConfig } from '$lib/stores/config.svelte';
  import { picker, refreshPicker } from '$lib/stores/picker.svelte';
  import { start, stop, timer } from '$lib/stores/timer.svelte';
  import { teamName } from '$lib/teams';

  interface Props {
    /** Called after a timer stops so the view can reload its entries. */
    onchange?: () => void;
  }

  let { onchange }: Props = $props();

  let description = $state('');
  let projectId = $state('');
  let taskId = $state('');
  let tagIds = $state<string[]>([]);
  let tasks = $state<Task[]>([]);
  let tagsOpen = $state(false);
  let tagsBox = $state<HTMLElement | undefined>();
  let billable = $state(false);
  let now = $state(Date.now());

  const running = $derived(timer.running);

  const elapsed = $derived(
    running ? Math.floor((now - Date.parse(running.started_at)) / 1000) : 0,
  );

  const activeProject = $derived(
    running?.project_id ? picker.projects.find((p) => p.id === running.project_id) : undefined,
  );

  /**
   * The team whose project the time goes on, running or about to start.
   * Shown next to the picker: those hours count in the team's report.
   */
  const team = $derived.by(() => {
    const project = running
      ? activeProject
      : picker.projects.find((candidate) => candidate.id === projectId);
    return teamName(project?.owner_team_id ?? null, picker.teams);
  });

  // A task belongs to one project: changing the project reloads the list and
  // clears the choice. The guard drops a late answer for a project left since.
  $effect(() => {
    const forProject = projectId;
    taskId = '';
    if (!forProject) {
      tasks = [];
      return;
    }
    void fetchTasks(forProject)
      .then((loaded) => {
        if (projectId === forProject) tasks = loaded;
      })
      .catch(() => (tasks = []));
  });

  // The tag box closes on a click outside it and on Escape.
  $effect(() => {
    if (!tagsOpen) return;
    const onclick = (event: MouseEvent): void => {
      if (tagsBox && !tagsBox.contains(event.target as Node)) tagsOpen = false;
    };
    const onkeydown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') tagsOpen = false;
    };
    document.addEventListener('click', onclick, true);
    document.addEventListener('keydown', onkeydown);
    return () => {
      document.removeEventListener('click', onclick, true);
      document.removeEventListener('keydown', onkeydown);
    };
  });

  // Load now, again once the mode is known (teams exist only on a server),
  // and whenever the window comes back: a lead may have added a project.
  $effect(() => {
    void appConfig.isServer;
    void refreshPicker();
    const onfocus = (): void => void refreshPicker();
    window.addEventListener('focus', onfocus);
    return () => window.removeEventListener('focus', onfocus);
  });

  // Tick only while something is running: no interval survives a stopped timer.
  $effect(() => {
    if (!timer.isRunning) return;
    now = Date.now();
    const handle = setInterval(() => (now = Date.now()), 1000);
    return () => clearInterval(handle);
  });

  export async function toggle(): Promise<void> {
    if (timer.isRunning) {
      await stop();
      description = '';
      onchange?.();
    } else {
      await start({
        description: description.trim() || null,
        project_id: projectId || null,
        task_id: taskId || null,
        tag_ids: tagIds,
        billable,
      });
      onchange?.();
    }
  }
</script>

<header class="bar">
  <input
    class="description"
    type="text"
    bind:value={description}
    placeholder={running ? (running.description ?? '') : t('timer.descriptionPlaceholder')}
    aria-label={t('timer.descriptionLabel')}
    disabled={timer.isRunning}
  />

  <label class="project">
    <span class="sr-only">{t('timer.project')}</span>
    <select bind:value={projectId} disabled={timer.isRunning}>
      <option value="">{t('timer.noProject')}</option>
      <ProjectOptions projects={picker.projects} teams={picker.teams} />
    </select>
  </label>

  {#if tasks.length > 0}
    <label class="task">
      <span class="sr-only">{t('entry.task')}</span>
      <select bind:value={taskId} disabled={timer.isRunning}>
        <option value="">{t('entry.noTask')}</option>
        {#each tasks as task (task.id)}
          <option value={task.id}>{task.name}</option>
        {/each}
      </select>
    </label>
  {/if}

  <div class="tags" bind:this={tagsBox}>
    <button
      type="button"
      class="tags-btn"
      class:chosen={tagIds.length > 0}
      onclick={() => (tagsOpen = !tagsOpen)}
      disabled={timer.isRunning}
      aria-expanded={tagsOpen}
      aria-label={t('entry.tags')}
      title={t('entry.tags')}
    >
      <TagIcon size={16} />
      {#if tagIds.length > 0}<span>{tagIds.length}</span>{/if}
    </button>
    {#if tagsOpen}
      <div class="tags-box">
        <TagPicker selected={tagIds} onchange={(ids) => (tagIds = ids)} />
      </div>
    {/if}
  </div>

  {#if team}
    <span class="team" title={t('timer.teamHint', { team })}>
      <Users size={14} />
      {team}
    </span>
  {/if}

  {#if activeProject}
    <span class="dot" style:--dot-color={activeProject.color} title={activeProject.name}></span>
  {/if}

  <label class="billable">
    <input type="checkbox" bind:checked={billable} disabled={timer.isRunning} />
    <span>{t('timer.billable')}</span>
  </label>

  <span class="clock" class:live={timer.isRunning}>{formatClock(elapsed)}</span>

  <button
    class="toggle"
    class:running={timer.isRunning}
    onclick={toggle}
    disabled={timer.busy}
    aria-label={timer.isRunning ? t('timer.stop') : t('timer.start')}
  >
    {#if timer.isRunning}
      <Square size={16} />
      {t('timer.stop')}
    {:else}
      <Play size={16} />
      {t('timer.start')}
    {/if}
  </button>
</header>

{#if timer.retrying}
  <p class="error" role="status">{t('timer.retrying')}</p>
{:else if timer.errorCode}
  <p class="error" role="alert">{t(`errors.${timer.errorCode}`)}</p>
{/if}

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-4);
    background-color: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
    flex-shrink: 0;
  }

  .tags {
    position: relative;
    flex-shrink: 0;
  }

  .tags-btn {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 34px;
    padding: 0 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .tags-btn:hover:not(:disabled) {
    background-color: var(--color-surface-hover);
  }

  .tags-btn.chosen {
    border-color: var(--color-accent);
    color: var(--color-accent);
  }

  .tags-btn:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .tags-btn:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  .tags-box {
    position: absolute;
    top: calc(100% + var(--space-2));
    left: 0;
    z-index: 20;
    width: 280px;
    padding: var(--space-3);
    background-color: var(--color-surface-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
  }

  .team {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    max-width: 160px;
    padding: 2px 8px;
    border: 1px solid var(--color-accent);
    border-radius: var(--radius-xl);
    color: var(--color-accent);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 0;
  }

  .description {
    flex: 1;
    min-width: 120px;
    padding: 7px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  .description:focus-visible,
  select:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  select {
    padding: 7px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
    cursor: pointer;
  }

  /* Project colour as a small dot, never a large filled area. */
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background-color: var(--dot-color);
    flex-shrink: 0;
  }

  .billable {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--text-sm);
    color: var(--color-text-muted);
    white-space: nowrap;
    cursor: pointer;
  }

  .clock {
    font-family: var(--font-mono);
    font-size: var(--text-xl);
    font-variant-numeric: tabular-nums;
    color: var(--color-text-muted);
    min-width: 9ch;
    text-align: right;
  }

  .clock.live {
    color: var(--color-text);
  }

  .toggle {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: 8px 18px;
    border: none;
    border-radius: var(--radius-sm);
    background-color: var(--color-accent);
    color: var(--color-on-accent);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s ease;
  }

  .toggle:hover:not(:disabled) {
    opacity: 0.9;
  }

  .toggle:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .toggle.running {
    background-color: var(--color-error);
    color: var(--color-surface);
  }

  .error {
    padding: var(--space-2) var(--space-4);
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
    color: var(--color-error);
    font-size: var(--text-sm);
    border-bottom: 1px solid var(--color-border);
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  /* A phone: the description gets its own line, the rest wraps under it.
     Last in the file, so it wins over the rules above. */
  /* The column it sits in (App.svelte), so an open sidebar counts too */
  @container main (max-width: 720px) {
    .bar {
      flex-wrap: wrap;
    }

    .description {
      flex-basis: 100%;
    }
  }
</style>
