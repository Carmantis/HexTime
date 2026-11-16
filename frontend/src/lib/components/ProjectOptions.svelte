<script lang="ts">
  /**
   * The <option>s of a project picker, grouped by owner: the user's own
   * projects, then one group per team. Goes inside a <select>, after its own
   * "no project" option.
   *
   * With only own projects (always so in local mode) there is nothing to
   * tell apart, so the options are listed without a group heading.
   */
  import type { Project, Team } from '$lib/api/types';
  import { t } from '$lib/i18n/index.svelte';
  import { groupProjects } from '$lib/teams';

  interface Props {
    projects: Project[];
    teams: Team[];
  }

  let { projects, teams }: Props = $props();

  const groups = $derived(groupProjects(projects, teams));
  const flat = $derived(groups.length === 1 && groups[0].teamId === null);
</script>

{#if flat}
  {#each groups[0].projects as project (project.id)}
    <option value={project.id}>{project.name}</option>
  {/each}
{:else}
  {#each groups as group (group.teamId ?? 'own')}
    <optgroup
      label={group.teamId === null
        ? t('timer.ownProjects')
        : (group.teamName ?? t('timer.otherTeam'))}
    >
      {#each group.projects as project (project.id)}
        <option value={project.id}>{project.name}</option>
      {/each}
    </optgroup>
  {/each}
{/if}
