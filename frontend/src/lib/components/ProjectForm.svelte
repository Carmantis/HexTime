<script lang="ts">
  import { untrack } from 'svelte';

  import { ApiError } from '$lib/api/client';
  import {
    archiveProject,
    createProject,
    restoreProject,
    updateProject,
    type ProjectInput,
  } from '$lib/api/projects';
  import type { Project, Team } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import ColorPicker from '$lib/components/ColorPicker.svelte';
  import OwnerSelect from '$lib/components/OwnerSelect.svelte';
  import TaskList from '$lib/components/TaskList.svelte';
  import { locale, t } from '$lib/i18n/index.svelte';
  import { centsToInput, parseCents } from '$lib/money';
  import { SWATCHES } from '$lib/palette';
  import { canChange, managedTeams, teamName } from '$lib/teams';

  interface Props {
    /** null means "create a new project". */
    project: Project | null;
    /** The user's teams (server mode); decides owner choices and editing. */
    teams?: Team[];
    onsaved: () => void;
    oncancel: () => void;
  }

  let { project, teams = [], onsaved, oncancel }: Props = $props();

  /** A team's project, seen by a plain member: shown, not changed. */
  const readonly = $derived(project !== null && !canChange(project, teams));
  let ownerTeamId = $state<string | null>(null);

  // One-time capture, as in EntryForm: the parent keys this component on the
  // project id, so it remounts with fresh state for each project.
  let name = $state(untrack(() => project?.name ?? ''));
  let clientName = $state(untrack(() => project?.client_name ?? ''));
  let color = $state<string>(untrack(() => project?.color ?? SWATCHES[0]));
  let billableDefault = $state(untrack(() => project?.billable_default ?? false));
  let rate = $state(
    untrack(() =>
      project?.hourly_rate_cents != null
        ? centsToInput(project.hourly_rate_cents, locale.current)
        : '',
    ),
  );

  let errorCode = $state<string | null>(null);
  let busy = $state(false);

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

  function save(): void {
    const parsed = parseCents(rate);
    if (parsed.kind === 'invalid') {
      errorCode = 'invalid_rate';
      return;
    }

    const input: ProjectInput = {
      name: name.trim(),
      client_name: clientName.trim() || null,
      color,
      billable_default: billableDefault,
      hourly_rate_cents: parsed.kind === 'ok' ? parsed.cents : null,
    };

    void run(() =>
      project ? updateProject(project.id, input) : createProject(input, ownerTeamId),
    );
  }

  function toggleArchived(): void {
    if (!project) return;
    const current = project;
    void run(() =>
      current.archived_at ? restoreProject(current.id) : archiveProject(current.id),
    );
  }
</script>

<div class="wrapper">
  <form
    class="form"
    onsubmit={(event) => {
      event.preventDefault();
      save();
    }}
  >
    {#if readonly}
      <p class="note">
        {t('teams.readOnlyProject', { team: teamName(project?.owner_team_id ?? null, teams) ?? '' })}
      </p>
    {/if}
    {#if !project}
      <OwnerSelect teams={managedTeams(teams)} bind:value={ownerTeamId} />
    {/if}

    <fieldset class="fields" disabled={readonly}>
      <label class="field">
        <span>{t('projects.name')}</span>
        <input type="text" bind:value={name} required maxlength="200" />
      </label>

      <label class="field">
        <span>{t('projects.client')}</span>
        <input type="text" bind:value={clientName} maxlength="200" />
      </label>

      <div class="row">
        <label class="field">
          <span>{t('projects.rate')}</span>
          <input
            type="text"
            inputmode="decimal"
            bind:value={rate}
            placeholder={t('projects.ratePlaceholder')}
          />
        </label>
        <label class="checkbox">
          <input type="checkbox" bind:checked={billableDefault} />
          <span>{t('projects.billableDefault')}</span>
        </label>
      </div>

      <div class="field">
        <span>{t('projects.color')}</span>
        <ColorPicker value={color} label={t('projects.color')} onchange={(c) => (color = c)} />
      </div>
    </fieldset>

    {#if errorCode}
      <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
    {/if}

    <div class="actions">
      {#if project && !readonly}
        <Button variant="secondary" onclick={toggleArchived} disabled={busy}>
          {project.archived_at ? t('projects.restore') : t('projects.archive')}
        </Button>
      {/if}
      <span class="spacer"></span>
      {#if readonly}
        <Button variant="primary" onclick={oncancel}>{t('common.close')}</Button>
      {:else}
        <Button variant="ghost" onclick={oncancel}>{t('entry.cancel')}</Button>
        <Button variant="primary" type="submit" disabled={busy || !name.trim()}>
          {t('entry.save')}
        </Button>
      {/if}
    </div>
  </form>

  <!-- Outside the <form>: its own input must not submit the project. -->
  {#if project}
    <TaskList projectId={project.id} {readonly} />
  {/if}
</div>

<style>
  .wrapper {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .form,
  .fields {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .fields {
    min-width: 0;
    margin: 0;
    padding: 0;
    border: none;
  }

  .note {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background-color: var(--color-surface-hover);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
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

  input[type='text'] {
    padding: 7px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  input[type='text']:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  .row {
    display: flex;
    align-items: flex-end;
    gap: var(--space-4);
  }

  .checkbox {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding-bottom: 8px;
    font-size: var(--text-sm);
    color: var(--color-text);
    white-space: nowrap;
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
