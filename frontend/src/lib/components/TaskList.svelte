<script lang="ts">
  import { Archive } from '@lucide/svelte';

  import { ApiError } from '$lib/api/client';
  import { archiveTask, createTask, fetchTasks } from '$lib/api/projects';
  import type { Task } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import { t } from '$lib/i18n/index.svelte';

  interface Props {
    projectId: string;
    /** A team's project seen by a plain member: list only. */
    readonly?: boolean;
  }

  let { projectId, readonly = false }: Props = $props();

  let tasks = $state<Task[]>([]);
  let name = $state('');
  let errorCode = $state<string | null>(null);

  async function load(): Promise<void> {
    tasks = await fetchTasks(projectId);
  }

  $effect(() => {
    void projectId;
    void load().catch(() => {});
  });

  async function attempt(action: () => Promise<unknown>): Promise<void> {
    errorCode = null;
    try {
      await action();
      await load();
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    }
  }

  function add(): void {
    const trimmed = name.trim();
    if (!trimmed) return;
    void attempt(async () => {
      await createTask(projectId, trimmed);
      name = '';
    });
  }

  function onkeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      add();
    }
  }
</script>

<section class="tasks">
  <h3>{t('projects.tasks')}</h3>

  {#if tasks.length === 0}
    <p class="none">{t('projects.noTasks')}</p>
  {:else}
    <ul>
      {#each tasks as task (task.id)}
        <li>
          <span>{task.name}</span>
          {#if !readonly}
            <button
              type="button"
              class="icon"
              onclick={() => void attempt(() => archiveTask(task.id))}
              aria-label={`${t('projects.archive')}: ${task.name}`}
              title={t('projects.archive')}
            >
              <Archive size={16} />
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  {#if !readonly}
    <div class="add">
      <input
        type="text"
        bind:value={name}
        {onkeydown}
        placeholder={t('projects.newTask')}
        aria-label={t('projects.newTask')}
      />
      <Button onclick={add} disabled={!name.trim()}>{t('projects.addTask')}</Button>
    </div>
  {/if}

  {#if errorCode}
    <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
  {/if}
</section>

<style>
  .tasks {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  h3 {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--color-text);
  }

  .none {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
  }

  ul {
    list-style: none;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }

  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px var(--space-3);
    font-size: var(--text-sm);
    color: var(--color-text);
    border-bottom: 1px solid var(--color-border-light);
  }

  li:last-child {
    border-bottom: none;
  }

  .icon {
    display: flex;
    padding: var(--space-1);
    border: none;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
  }

  .icon:hover {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  .add {
    display: flex;
    gap: var(--space-2);
  }

  input {
    flex: 1;
    padding: 7px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  input:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  .error {
    font-size: var(--text-sm);
    color: var(--color-error);
  }
</style>
