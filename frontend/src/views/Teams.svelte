<script lang="ts">
  /**
   * Teams (server mode): the user's teams, their members and invitations.
   *
   * Whoever creates a team is its lead. A lead invites people already in the
   * organisation; they join by saying yes in the app (InvitationPrompt). The
   * organisation administrator sees every team but runs one only when it has
   * no lead left. The backend (services/teams.py) decides all of this; the
   * view only hides what would be refused.
   */
  import { LogOut, Pencil, Plus, Trash2, UserMinus, X } from '@lucide/svelte';

  import { ApiError } from '$lib/api/client';
  import {
    cancelInvitation,
    changeRole,
    createTeam,
    deleteTeam,
    fetchInvitations,
    fetchMembers,
    fetchTeams,
    findPeople,
    invite,
    removeMember,
    renameTeam,
  } from '$lib/api/teams';
  import type { Person, Team, TeamInvitation, TeamMember, TeamRole } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { refreshPicker } from '$lib/stores/picker.svelte';
  import { session } from '$lib/stores/session.svelte';

  const ROLES: TeamRole[] = ['member', 'lead'];
  /** Wait this long after the last keystroke before searching. */
  const SEARCH_DELAY_MS = 250;

  let teams = $state<Team[]>([]);
  let selectedId = $state<string | null>(null);
  let members = $state<TeamMember[]>([]);
  let invitations = $state<TeamInvitation[]>([]);
  let loading = $state(true);
  let notice = $state<string | null>(null);
  let errorCode = $state<string | null>(null);
  let busy = $state(false);

  /** `undefined` = closed, `null` = a new team, a team = renaming it. */
  let nameDialog = $state<Team | null | undefined>(undefined);
  let nameInput = $state('');

  // Inviting: a search over the organisation's people.
  let search = $state('');
  let found = $state<Person[]>([]);

  const selected = $derived(teams.find((team) => team.id === selectedId) ?? null);
  const canManage = $derived(selected?.can_manage ?? false);
  /** People to offer: not in the team and not waiting on an answer already. */
  const offered = $derived.by(() => {
    const taken = new Set([
      ...members.map((member) => member.user_id),
      ...invitations.map((invitation) => invitation.user_id),
    ]);
    return found.filter((person) => !taken.has(person.id));
  });

  function fail(error: unknown): void {
    errorCode = error instanceof ApiError ? error.code : 'unknown_error';
  }

  async function loadTeams(): Promise<void> {
    try {
      teams = await fetchTeams();
      if (!teams.some((team) => team.id === selectedId)) selectedId = teams[0]?.id ?? null;
    } catch (error) {
      fail(error);
    } finally {
      loading = false;
    }
  }

  async function loadTeam(teamId: string): Promise<void> {
    try {
      [members, invitations] = await Promise.all([
        fetchMembers(teamId),
        fetchInvitations(teamId),
      ]);
    } catch (error) {
      fail(error);
    }
  }

  $effect(() => {
    void loadTeams();
  });

  $effect(() => {
    if (selectedId) {
      void loadTeam(selectedId);
    } else {
      members = [];
      invitations = [];
    }
  });

  // Search as the lead types, after a short pause. An empty box finds nobody.
  $effect(() => {
    const words = search.trim();
    if (!words) {
      found = [];
      return;
    }
    const timer = setTimeout(() => {
      findPeople(words)
        .then((people) => {
          if (search.trim() === words) found = people;
        })
        .catch(fail);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  });

  /**
   * Run a change, then show the fresh state of the lists. An action that
   * returns a string has it shown as the notice.
   */
  async function act(action: () => Promise<unknown>): Promise<void> {
    busy = true;
    notice = null;
    errorCode = null;
    try {
      const result = await action();
      notice = typeof result === 'string' ? result : null;
      await loadTeams();
      if (selectedId) await loadTeam(selectedId);
      // Leaving or deleting a team takes its projects out of the pickers.
      void refreshPicker();
    } catch (error) {
      fail(error);
    } finally {
      busy = false;
    }
  }

  function openNameDialog(team: Team | null): void {
    nameInput = team?.name ?? '';
    nameDialog = team;
  }

  async function saveName(): Promise<void> {
    const name = nameInput.trim();
    if (!name || nameDialog === undefined) return;
    const renaming = nameDialog;
    nameDialog = undefined;
    await act(async () => {
      if (renaming) {
        await renameTeam(renaming.id, name);
      } else {
        selectedId = (await createTeam(name)).id;
      }
    });
  }

  function select(team: Team): void {
    selectedId = team.id;
    notice = null;
    errorCode = null;
    search = '';
  }

  function invitePerson(person: Person): void {
    const team = selected;
    if (!team) return;
    void act(async () => {
      await invite(team.id, person.id);
      search = '';
      return t('teams.invited', { name: person.display_name });
    });
  }

  function cancel(invitation: TeamInvitation): void {
    const team = selected;
    if (team) void act(() => cancelInvitation(team.id, invitation.user_id));
  }

  function remove(member: TeamMember): void {
    const team = selected;
    if (!team || !confirm(t('teams.confirmRemove', { name: member.display_name }))) return;
    void act(() => removeMember(team.id, member.user_id));
  }

  function leave(): void {
    const team = selected;
    const me = session.user;
    if (!team || !me || !confirm(t('teams.confirmLeave', { team: team.name }))) return;
    void act(() => removeMember(team.id, me.id));
  }

  function removeTeam(): void {
    const team = selected;
    if (!team || !confirm(t('teams.confirmDelete', { team: team.name }))) return;
    void act(() => deleteTeam(team.id));
  }
</script>

<section class="view">
  <header class="head">
    <h1>{t('teams.title')}</h1>
    <Button variant="primary" onclick={() => openNameDialog(null)}>
      <Plus size={16} />
      {t('teams.new')}
    </Button>
  </header>

  {#if notice}
    <p class="notice" role="status">{notice}</p>
  {/if}
  {#if errorCode}
    <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
  {/if}

  {#if loading}
    <p class="muted">{t('common.loading')}</p>
  {:else if teams.length === 0}
    <div class="card">
      <EmptyState title={t('teams.emptyTitle')} body={t('teams.emptyBody')}>
        {#snippet action()}
          <Button variant="primary" onclick={() => openNameDialog(null)}>{t('teams.new')}</Button>
        {/snippet}
      </EmptyState>
    </div>
  {:else}
    <div class="layout">
      <nav class="card list" aria-label={t('teams.title')}>
        {#each teams as team (team.id)}
          <button
            class="team"
            class:active={team.id === selectedId}
            aria-current={team.id === selectedId ? 'true' : undefined}
            onclick={() => select(team)}
          >
            <span class="team-name">{team.name}</span>
            <span class="meta">
              {team.role ? t(`teams.role_${team.role}`) : t('teams.notMember')} ·
              {t('teams.memberCount', { count: team.member_count })}
              {#if !team.has_lead}· <span class="warn">{t('teams.noLead')}</span>{/if}
            </span>
          </button>
        {/each}
      </nav>

      {#if selected}
        <div class="card detail">
          <header class="card-head">
            <h2>{selected.name}</h2>
            <div class="tools">
              {#if canManage}
                <button
                  class="icon"
                  onclick={() => openNameDialog(selected)}
                  title={t('teams.rename')}
                  aria-label={t('teams.rename')}
                >
                  <Pencil size={16} />
                </button>
                <button
                  class="icon"
                  onclick={removeTeam}
                  disabled={busy}
                  title={t('teams.delete')}
                  aria-label={t('teams.delete')}
                >
                  <Trash2 size={16} />
                </button>
              {/if}
              {#if selected.role}
                <button
                  class="icon"
                  onclick={leave}
                  disabled={busy}
                  title={t('teams.leave')}
                  aria-label={t('teams.leave')}
                >
                  <LogOut size={16} />
                </button>
              {/if}
            </div>
          </header>

          {#if !selected.has_lead && session.user?.is_admin}
            <p class="stand-in">{t('teams.standIn')}</p>
          {/if}

          <table>
            <thead>
              <tr>
                <th>{t('admin.name')}</th>
                <th class="email">{t('admin.email')}</th>
                <th>{t('teams.role')}</th>
                <th><span class="sr-only">{t('teams.remove')}</span></th>
              </tr>
            </thead>
            <tbody>
              {#each members as member (member.user_id)}
                {@const me = member.user_id === session.user?.id}
                <tr class:disabled={member.status === 'disabled'}>
                  <td>
                    {member.display_name}
                    {#if me}<span class="muted-inline">({t('admin.you')})</span>{/if}
                    {#if member.status === 'disabled'}
                      <span class="pending">{t('admin.statusDisabled')}</span>
                    {/if}
                  </td>
                  <td class="email">{member.email}</td>
                  <td>
                    {#if canManage}
                      <select
                        value={member.role}
                        disabled={busy}
                        aria-label={t('teams.roleOf', { name: member.display_name })}
                        onchange={(event) => {
                          const team = selected;
                          const next = event.currentTarget.value as TeamRole;
                          if (team) void act(() => changeRole(team.id, member.user_id, next));
                        }}
                      >
                        {#each ROLES as option (option)}
                          <option value={option}>{t(`teams.role_${option}`)}</option>
                        {/each}
                      </select>
                    {:else}
                      {t(`teams.role_${member.role}`)}
                    {/if}
                  </td>
                  <td>
                    <div class="actions">
                      {#if canManage && !me}
                        <button
                          class="icon"
                          disabled={busy}
                          onclick={() => remove(member)}
                          title={t('teams.remove')}
                          aria-label={`${t('teams.remove')}: ${member.display_name}`}
                        >
                          <UserMinus size={16} />
                        </button>
                      {/if}
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>

          {#if invitations.length > 0}
            <section class="invitations">
              <h3>{t('teams.waiting')}</h3>
              <ul>
                {#each invitations as invitation (invitation.user_id)}
                  <li>
                    <span>{invitation.display_name}</span>
                    <span class="email">{invitation.email}</span>
                    {#if canManage}
                      <button
                        class="icon"
                        disabled={busy}
                        onclick={() => cancel(invitation)}
                        title={t('teams.cancelInvitation')}
                        aria-label={`${t('teams.cancelInvitation')}: ${invitation.display_name}`}
                      >
                        <X size={16} />
                      </button>
                    {/if}
                  </li>
                {/each}
              </ul>
            </section>
          {/if}

          {#if canManage}
            <section class="add">
              <h3>{t('teams.invitePerson')}</h3>
              <input
                type="search"
                bind:value={search}
                placeholder={t('teams.searchPlaceholder')}
                aria-label={t('teams.invitePerson')}
              />
              {#if search.trim()}
                {#if offered.length === 0}
                  <p class="hint">{t('teams.nobodyFound')}</p>
                {:else}
                  <ul class="found">
                    {#each offered as person (person.id)}
                      <li>
                        <span>{person.display_name}</span>
                        <span class="email">{person.email}</span>
                        <Button onclick={() => invitePerson(person)} disabled={busy}>
                          {t('teams.invite')}
                        </Button>
                      </li>
                    {/each}
                  </ul>
                {/if}
              {/if}
              <p class="hint">{t('teams.inviteHelp')}</p>
            </section>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</section>

{#if nameDialog !== undefined}
  <Modal
    title={nameDialog ? t('teams.rename') : t('teams.new')}
    onclose={() => (nameDialog = undefined)}
  >
    <form
      id="team-name"
      onsubmit={(event) => {
        event.preventDefault();
        void saveName();
      }}
    >
      <label class="field">
        <span>{t('teams.name')}</span>
        <!-- svelte-ignore a11y_autofocus -->
        <input type="text" bind:value={nameInput} required maxlength="200" autofocus />
      </label>
      {#if !nameDialog}
        <p class="hint">{t('teams.newHelp')}</p>
      {/if}
    </form>
    {#snippet footer()}
      <Button variant="ghost" onclick={() => (nameDialog = undefined)}>
        {t('entry.cancel')}
      </Button>
      <Button variant="primary" onclick={() => void saveName()} disabled={!nameInput.trim()}>
        {t('entry.save')}
      </Button>
    {/snippet}
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

  h3 {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--color-text);
  }

  .layout {
    display: grid;
    grid-template-columns: minmax(180px, 240px) minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }

  @media (max-width: 760px) {
    .layout {
      grid-template-columns: minmax(0, 1fr);
    }
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

  .list {
    display: flex;
    flex-direction: column;
  }

  .team {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-3) var(--space-4);
    border: none;
    border-bottom: 1px solid var(--color-border-light);
    border-left: 3px solid transparent;
    background: none;
    text-align: left;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .team:last-child {
    border-bottom: none;
  }

  .team:hover {
    background-color: var(--color-surface-hover);
  }

  .team.active {
    border-left-color: var(--color-accent);
    background-color: var(--color-surface-hover);
  }

  .team:focus-visible,
  .icon:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -2px;
  }

  .team-name {
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: 500;
  }

  .meta,
  .hint,
  .muted-inline {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
  }

  .muted-inline {
    margin-left: var(--space-1);
  }

  .pending {
    margin-left: var(--space-2);
    color: var(--color-warning);
    font-size: var(--text-xs);
  }

  .tools,
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-1);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }

  th {
    padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--color-border);
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: 500;
    text-align: left;
  }

  td {
    padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--color-border-light);
    color: var(--color-text);
    vertical-align: middle;
  }

  .email {
    color: var(--color-text-muted);
  }

  .add {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-4);
    border-top: 1px solid var(--color-border);
  }

  .invitations {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4);
    border-top: 1px solid var(--color-border);
  }

  .invitations ul,
  .found {
    list-style: none;
  }

  .invitations li,
  .found li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) auto;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-1) 0;
    font-size: var(--text-sm);
    color: var(--color-text);
  }

  .found {
    border: 1px solid var(--color-border-light);
    border-radius: var(--radius-sm);
    padding: 0 var(--space-3);
    max-height: 220px;
    overflow-y: auto;
  }

  .found li + li {
    border-top: 1px solid var(--color-border-light);
  }

  .stand-in {
    margin: var(--space-3) var(--space-4) 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background-color: color-mix(in srgb, var(--color-warning) 12%, transparent);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  .warn {
    color: var(--color-warning);
  }

  tr.disabled td {
    color: var(--color-text-muted);
  }

  input,
  select {
    padding: 7px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  input:focus-visible,
  select:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-bottom: var(--space-2);
  }

  .field > span {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--color-text-muted);
  }

  .icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border: none;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .icon:hover:not(:disabled) {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  .icon:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .notice,
  .error {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
  }

  .notice {
    background-color: color-mix(in srgb, var(--color-success) 12%, transparent);
    color: var(--color-text);
  }

  .error {
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
    color: var(--color-error);
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  /* A phone has no room for the members table's address column; the name is
     enough there. Invitations and search results keep their addresses: they
     tell two people of the same name apart. */
  @media (max-width: 720px) {
    th.email,
    td.email {
      display: none;
    }
  }
</style>
