<script lang="ts">
  /**
   * Whose a new project or tag is: one's own, or a team's. Shown only when
   * the user leads at least one team; otherwise everything is their own.
   */
  import type { Team } from '$lib/api/types';
  import { t } from '$lib/i18n/index.svelte';

  interface Props {
    /** Teams the user leads or administers. */
    teams: Team[];
    /** null = one's own. */
    value: string | null;
  }

  let { teams, value = $bindable() }: Props = $props();
</script>

{#if teams.length > 0}
  <label class="field">
    <span>{t('teams.owner')}</span>
    <select bind:value>
      <option value={null}>{t('teams.ownerSelf')}</option>
      {#each teams as team (team.id)}
        <option value={team.id}>{t('teams.ownerTeam', { name: team.name })}</option>
      {/each}
    </select>
  </label>
{/if}

<style>
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

  select {
    padding: 7px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  select:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }
</style>
