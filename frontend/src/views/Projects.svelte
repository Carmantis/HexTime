<script lang="ts">
  import { Plus } from '@lucide/svelte';

  import { fetchProjects } from '$lib/api/projects';
  import { fetchTags } from '$lib/api/tags';
  import { fetchTeams } from '$lib/api/teams';
  import type { Project, Tag, Team } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import ProjectForm from '$lib/components/ProjectForm.svelte';
  import TagForm from '$lib/components/TagForm.svelte';
  import { locale, t } from '$lib/i18n/index.svelte';
  import { formatCents } from '$lib/money';
  import { appConfig } from '$lib/stores/config.svelte';
  import { refreshPicker } from '$lib/stores/picker.svelte';
  import { teamName } from '$lib/teams';

  let projects = $state<Project[]>([]);
  let tags = $state<Tag[]>([]);
  /** Server mode: whose projects these are and what the user may change. */
  let teams = $state<Team[]>([]);
  let loading = $state(true);
  let showArchived = $state(false);

  // `undefined` = closed, `null` = creating, a row = editing that row.
  let projectDialog = $state<Project | null | undefined>(undefined);
  let tagDialog = $state<Tag | null | undefined>(undefined);

  async function load(): Promise<void> {
    const [loadedProjects, loadedTags, loadedTeams] = await Promise.all([
      fetchProjects(showArchived),
      fetchTags(showArchived),
      appConfig.isServer ? fetchTeams() : Promise.resolve([]),
    ]);
    projects = loadedProjects;
    tags = loadedTags;
    teams = loadedTeams;
    loading = false;
  }

  $effect(() => {
    void showArchived;
    void load().catch(() => (loading = false));
  });

  function saved(): void {
    projectDialog = undefined;
    tagDialog = undefined;
    void load();
    // The timer bar offers these too.
    void refreshPicker();
  }
</script>

<section class="view">
  <header class="head">
    <h1>{t('projects.title')}</h1>
    <label class="toggle">
      <input type="checkbox" bind:checked={showArchived} />
      <span>{t('projects.showArchived')}</span>
    </label>
  </header>

  <div class="card">
    <header class="card-head">
      <h2>{t('projects.title')}</h2>
      <Button variant="primary" onclick={() => (projectDialog = null)}>
        <Plus size={16} />
        {t('projects.new')}
      </Button>
    </header>

    {#if loading}
      <p class="muted">{t('common.loading')}</p>
    {:else if projects.length === 0}
      <EmptyState title={t('projects.emptyTitle')} body={t('projects.emptyBody')}>
        {#snippet action()}
          <Button variant="primary" onclick={() => (projectDialog = null)}>
            {t('projects.new')}
          </Button>
        {/snippet}
      </EmptyState>
    {:else}
      <ul class="rows">
        {#each projects as project (project.id)}
          <li>
            <button
              class="row"
              class:archived={project.archived_at}
              style:--project-color={project.color}
              onclick={() => (projectDialog = project)}
            >
              <span class="dot"></span>
              <span class="name">{project.name}</span>
              {#if project.client_name}
                <span class="meta">{project.client_name}</span>
              {/if}
              {#if project.owner_team_id}
                <span class="badge team">{teamName(project.owner_team_id, teams)}</span>
              {/if}
              {#if project.archived_at}
                <span class="badge">{t('projects.archived')}</span>
              {/if}
              <span class="rate">
                {project.hourly_rate_cents != null
                  ? `${formatCents(project.hourly_rate_cents, locale.current, project.currency)} / h`
                  : '—'}
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

  <div class="card">
    <header class="card-head">
      <h2>{t('tags.title')}</h2>
      <Button onclick={() => (tagDialog = null)}>
        <Plus size={16} />
        {t('tags.new')}
      </Button>
    </header>

    {#if !loading && tags.length === 0}
      <EmptyState title={t('tags.emptyTitle')} body={t('tags.emptyBody')} />
    {:else}
      <div class="chips">
        {#each tags as tag (tag.id)}
          <button
            class="chip"
            class:archived={tag.archived_at}
            style:--tag-color={tag.color}
            onclick={() => (tagDialog = tag)}
            title={teamName(tag.owner_team_id, teams) ?? undefined}
          >
            <span class="dot"></span>
            {tag.name}
            {#if tag.owner_team_id}
              <span class="chip-team">· {teamName(tag.owner_team_id, teams)}</span>
            {/if}
          </button>
        {/each}
      </div>
    {/if}
  </div>
</section>

{#if projectDialog !== undefined}
  <Modal
    title={projectDialog ? t('projects.edit') : t('projects.new')}
    onclose={() => (projectDialog = undefined)}
  >
    {#key projectDialog?.id ?? 'new'}
      <ProjectForm
        project={projectDialog}
        {teams}
        onsaved={saved}
        oncancel={() => (projectDialog = undefined)}
      />
    {/key}
  </Modal>
{/if}

{#if tagDialog !== undefined}
  <Modal
    title={tagDialog ? t('tags.edit') : t('tags.new')}
    onclose={() => (tagDialog = undefined)}
  >
    {#key tagDialog?.id ?? 'new'}
      <TagForm tag={tagDialog} {teams} onsaved={saved} oncancel={() => (tagDialog = undefined)} />
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

  .head,
  .card-head {
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

  h2 {
    font-size: var(--text-base);
    font-weight: 600;
    color: var(--color-text);
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
    color: var(--color-text-muted);
    cursor: pointer;
  }

  .card {
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .card-head {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--color-border);
  }

  .muted {
    padding: var(--space-5);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .rows {
    list-style: none;
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-3) var(--space-4);
    border: none;
    border-bottom: 1px solid var(--color-border-light);
    background: none;
    text-align: left;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  li:last-child .row {
    border-bottom: none;
  }

  .row:hover {
    background-color: var(--color-surface-hover);
  }

  .row:focus-visible,
  .chip:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -2px;
  }

  .archived {
    opacity: 0.55;
  }

  /* Project colour as a small dot, never a large filled area. */
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background-color: var(--project-color, var(--tag-color));
    flex-shrink: 0;
  }

  .name {
    flex: 1;
    min-width: 0;
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .meta {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
  }

  .badge {
    padding: 1px 8px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    font-size: 10px;
    color: var(--color-text-muted);
  }

  .badge.team {
    border-color: var(--color-accent);
    color: var(--color-accent);
  }

  .chip-team {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
  }

  .rate {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    padding: var(--space-4);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 4px 12px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    background-color: color-mix(in srgb, var(--tag-color) 14%, transparent);
    color: var(--color-text);
    font-size: var(--text-sm);
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .chip:hover {
    background-color: color-mix(in srgb, var(--tag-color) 24%, transparent);
  }
</style>
