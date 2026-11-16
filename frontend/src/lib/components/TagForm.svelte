<script lang="ts">
  import { untrack } from 'svelte';

  import { ApiError } from '$lib/api/client';
  import { archiveTag, createTag, restoreTag, updateTag } from '$lib/api/tags';
  import type { Tag, Team } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import ColorPicker from '$lib/components/ColorPicker.svelte';
  import OwnerSelect from '$lib/components/OwnerSelect.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { SWATCHES } from '$lib/palette';
  import { canChange, managedTeams, teamName } from '$lib/teams';

  interface Props {
    /** null means "create a new tag". */
    tag: Tag | null;
    /** The user's teams (server mode); decides owner choices and editing. */
    teams?: Team[];
    onsaved: () => void;
    oncancel: () => void;
  }

  let { tag, teams = [], onsaved, oncancel }: Props = $props();

  /** A team's tag, seen by a plain member: shown, not changed. */
  const readonly = $derived(tag !== null && !canChange(tag, teams));
  let ownerTeamId = $state<string | null>(null);

  let name = $state(untrack(() => tag?.name ?? ''));
  let color = $state<string>(untrack(() => tag?.color ?? SWATCHES[0]));
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
    const input = { name: name.trim(), color };
    void run(() => (tag ? updateTag(tag.id, input) : createTag(input, ownerTeamId)));
  }

  function toggleArchived(): void {
    if (!tag) return;
    const current = tag;
    void run(() => (current.archived_at ? restoreTag(current.id) : archiveTag(current.id)));
  }
</script>

<form
  class="form"
  onsubmit={(event) => {
    event.preventDefault();
    save();
  }}
>
  {#if readonly}
    <p class="note">
      {t('teams.readOnlyTag', { team: teamName(tag?.owner_team_id ?? null, teams) ?? '' })}
    </p>
  {/if}
  {#if !tag}
    <OwnerSelect teams={managedTeams(teams)} bind:value={ownerTeamId} />
  {/if}

  <fieldset class="fields" disabled={readonly}>
    <label class="field">
      <span>{t('tags.name')}</span>
      <input type="text" bind:value={name} required maxlength="100" />
    </label>

    <div class="field">
      <span>{t('projects.color')}</span>
      <ColorPicker value={color} label={t('projects.color')} onchange={(c) => (color = c)} />
    </div>
  </fieldset>

  {#if errorCode}
    <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
  {/if}

  <div class="actions">
    {#if tag && !readonly}
      <Button variant="secondary" onclick={toggleArchived} disabled={busy}>
        {tag.archived_at ? t('projects.restore') : t('projects.archive')}
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

<style>
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
  }

  .field > span {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--color-text-muted);
  }

  input {
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
