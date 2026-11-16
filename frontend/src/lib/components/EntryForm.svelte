<script lang="ts">
  import { untrack } from 'svelte';

  import { ApiError } from '$lib/api/client';
  import { createEntry, deleteEntry, updateEntry } from '$lib/api/entries';
  import { fetchTasks } from '$lib/api/projects';
  import type { Task, TimeEntry, TimeEntryInput } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import ProjectOptions from '$lib/components/ProjectOptions.svelte';
  import TagPicker from '$lib/components/TagPicker.svelte';
  import TimeInput from '$lib/components/TimeInput.svelte';
  import { fromDateAndTime, startOfDay, toDateInput, toTimeInput } from '$lib/format';
  import { t } from '$lib/i18n/index.svelte';
  import { picker, refreshPicker } from '$lib/stores/picker.svelte';

  interface Props {
    /** null means "create a new entry". */
    entry: TimeEntry | null;
    /** For a new entry: the local day (YYYY-MM-DD) to put it on. */
    day?: string;
    onsaved: () => void;
    oncancel: () => void;
  }

  let { entry, day, onsaved, oncancel }: Props = $props();

  // A new entry must not start where it ends, or the first save is a 422.
  // Default to "the hour that just ended", rounded to five minutes — or, on a
  // chosen calendar day, 09:00–10:00.
  const fallbackEnd = new Date(Math.floor(Date.now() / 300_000) * 300_000);
  const fallbackStart = new Date(
    Math.max(fallbackEnd.getTime() - 3_600_000, startOfDay(fallbackEnd).getTime()),
  );

  function initialDate(): string {
    if (entry) return toDateInput(entry.started_at);
    return day ?? toDateInput(fallbackEnd.toISOString());
  }

  function initialStart(): string {
    if (entry) return toTimeInput(entry.started_at);
    return day ? '09:00' : toTimeInput(fallbackStart.toISOString());
  }

  function initialEnd(): string {
    // A running entry is offered "now" as its end, not its own start.
    if (entry) return toTimeInput(entry.ended_at ?? fallbackEnd.toISOString());
    return day ? '10:00' : toTimeInput(fallbackEnd.toISOString());
  }

  // untrack() marks these prop reads as a deliberate one-time capture rather
  // than a missed subscription. Tracking.svelte keys this component on the
  // entry id, so it remounts with fresh state whenever a different entry is
  // opened — the same pattern HexCalendar uses in EventModal.
  let date = $state(untrack(initialDate));
  let startTime = $state(untrack(initialStart));
  let endTime = $state(untrack(initialEnd));
  let description = $state(untrack(() => entry?.description ?? ''));
  let projectId = $state(untrack(() => entry?.project_id ?? ''));
  let billable = $state(untrack(() => entry?.billable ?? false));
  let tagIds = $state<string[]>(untrack(() => (entry ? entry.tags.map((tag) => tag.id) : [])));
  let taskId = $state(untrack(() => entry?.task_id ?? ''));
  let tasks = $state<Task[]>([]);

  let errorCode = $state<string | null>(null);
  let busy = $state(false);
  let confirmingDelete = $state(false);

  // The shared list may be a little old (a team project added since).
  $effect(() => {
    void refreshPicker();
  });

  // Tasks belong to a project, so they reload whenever the project changes.
  // The guard drops a late answer for a project the user already left.
  $effect(() => {
    const forProject = projectId;
    if (!forProject) {
      tasks = [];
      return;
    }
    void fetchTasks(forProject)
      .then((loaded) => {
        if (projectId === forProject) tasks = loaded;
      })
      .catch(() => {});
  });

  async function run(action: () => Promise<unknown>): Promise<void> {
    busy = true;
    errorCode = null;
    try {
      await action();
      onsaved();
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    } finally {
      busy = false;
    }
  }

  function save(): Promise<void> {
    const input: TimeEntryInput = {
      started_at: fromDateAndTime(date, startTime),
      ended_at: fromDateAndTime(date, endTime),
      description: description.trim() || null,
      project_id: projectId || null,
      task_id: taskId || null,
      billable,
      tag_ids: tagIds,
    };

    return run(() => (entry ? updateEntry(entry.id, input) : createEntry(input)));
  }

  function remove(): Promise<void> | void {
    if (!entry) return;
    if (!confirmingDelete) {
      confirmingDelete = true;
      return;
    }
    return run(() => deleteEntry(entry.id));
  }
</script>

<form
  class="form"
  onsubmit={(event) => {
    event.preventDefault();
    void save();
  }}
>
  <label class="field">
    <span>{t('timer.descriptionLabel')}</span>
    <input type="text" bind:value={description} placeholder={t('timer.descriptionPlaceholder')} />
  </label>

  <div class="row">
    <label class="field">
      <span>{t('entry.date')}</span>
      <input type="date" bind:value={date} required />
    </label>
    <label class="field">
      <span>{t('entry.start')}</span>
      <TimeInput bind:value={startTime} required />
    </label>
    <label class="field">
      <span>{t('entry.end')}</span>
      <TimeInput bind:value={endTime} required />
    </label>
  </div>

  <label class="field">
    <span>{t('timer.project')}</span>
    <!-- A task belongs to one project, so changing project clears it. -->
    <select bind:value={projectId} onchange={() => (taskId = '')}>
      <option value="">{t('timer.noProject')}</option>
      <ProjectOptions projects={picker.projects} teams={picker.teams} />
    </select>
  </label>

  {#if projectId && tasks.length > 0}
    <label class="field">
      <span>{t('entry.task')}</span>
      <select bind:value={taskId}>
        <option value="">{t('entry.noTask')}</option>
        {#each tasks as task (task.id)}
          <option value={task.id}>{task.name}</option>
        {/each}
      </select>
    </label>
  {/if}

  <div class="field">
    <span>{t('entry.tags')}</span>
    <TagPicker selected={tagIds} onchange={(ids) => (tagIds = ids)} />
  </div>

  <label class="checkbox">
    <input type="checkbox" bind:checked={billable} />
    <span>{t('timer.billable')}</span>
  </label>

  {#if errorCode}
    <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
  {/if}

  <div class="actions">
    {#if entry}
      <Button variant="danger" onclick={() => void remove()}>
        {confirmingDelete ? t('entry.confirmDelete') : t('entry.delete')}
      </Button>
    {/if}
    <span class="spacer"></span>
    <Button variant="ghost" onclick={oncancel}>{t('entry.cancel')}</Button>
    <Button variant="primary" type="submit" disabled={busy}>{t('entry.save')}</Button>
  </div>
</form>

<style>
  .form {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    flex: 1;
    min-width: 0;
  }

  .field > span {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--color-text-muted);
  }

  input[type='text'],
  input[type='date'],
  select {
    padding: 7px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
    width: 100%;
  }

  input:focus-visible,
  select:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  .row {
    display: flex;
    gap: var(--space-3);
  }

  .checkbox {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
    color: var(--color-text);
    cursor: pointer;
  }

  .error {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
    color: var(--color-error);
    font-size: var(--text-sm);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .spacer {
    flex: 1;
  }
</style>
