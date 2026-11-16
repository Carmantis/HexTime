<script lang="ts">
  /**
   * The organisation administrator's list of people (server mode).
   *
   * The backend refuses all of this to anyone else; hiding the page in the
   * sidebar is only a convenience.
   */
  import { Mail, Shield, ShieldOff, UserCheck, UserPlus, UserX } from '@lucide/svelte';

  import { fetchUsers, sendLink, updateUser } from '$lib/api/admin';
  import { ApiError } from '$lib/api/client';
  import type { AdminUser, UserStatus } from '$lib/api/types';
  import AddPeople from '$lib/components/AddPeople.svelte';
  import Button from '$lib/components/Button.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { session } from '$lib/stores/session.svelte';

  const STATUS_KEYS: Record<UserStatus, string> = {
    active: 'admin.statusActive',
    invited: 'admin.statusInvited',
    unverified: 'admin.statusUnverified',
    disabled: 'admin.statusDisabled',
  };

  let users = $state<AdminUser[]>([]);
  let loading = $state(true);
  let adding = $state(false);
  /** The row an action is running on, so only its buttons wait. */
  let busyId = $state<string | null>(null);
  let notice = $state<string | null>(null);
  let errorCode = $state<string | null>(null);

  async function load(): Promise<void> {
    try {
      users = await fetchUsers();
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    void load();
  });

  async function act(user: AdminUser, action: () => Promise<unknown>, done?: string) {
    busyId = user.id;
    notice = null;
    errorCode = null;
    try {
      await action();
      notice = done ?? null;
      await load();
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    } finally {
      busyId = null;
    }
  }

  function toggleActive(user: AdminUser): void {
    if (user.is_active && !confirm(t('admin.confirmDisable', { name: user.display_name }))) {
      return;
    }
    void act(user, () => updateUser(user.id, { is_active: !user.is_active }));
  }
</script>

<section class="view">
  <header class="head">
    <h1>{t('admin.title')}</h1>
    <Button variant="primary" onclick={() => (adding = true)}>
      <UserPlus size={16} />
      {t('admin.addPeople')}
    </Button>
  </header>

  {#if notice}
    <p class="notice" role="status">{notice}</p>
  {/if}
  {#if errorCode}
    <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
  {/if}

  <div class="card">
    {#if loading}
      <p class="muted">{t('common.loading')}</p>
    {:else if users.length <= 1}
      <EmptyState title={t('admin.emptyTitle')} body={t('admin.emptyBody')}>
        {#snippet action()}
          <Button variant="primary" onclick={() => (adding = true)}>{t('admin.addPeople')}</Button>
        {/snippet}
      </EmptyState>
    {/if}

    {#if !loading && users.length > 0}
      <table>
        <thead>
          <tr>
            <th>{t('admin.name')}</th>
            <th class="email">{t('admin.email')}</th>
            <th>{t('admin.status')}</th>
            <th><span class="sr-only">{t('admin.title')}</span></th>
          </tr>
        </thead>
        <tbody>
          {#each users as user (user.id)}
            {@const me = user.id === session.user?.id}
            <tr class:disabled={!user.is_active}>
              <td>
                {user.display_name}
                {#if me}<span class="muted">({t('admin.you')})</span>{/if}
                {#if user.is_admin}<span class="badge">{t('admin.adminBadge')}</span>{/if}
              </td>
              <td class="email">{user.email}</td>
              <td><span class="status {user.status}">{t(STATUS_KEYS[user.status])}</span></td>
              <td>
                <div class="actions">
                  {#if user.is_active}
                    <button
                      class="icon"
                      disabled={busyId === user.id}
                      onclick={() =>
                        void act(
                          user,
                          () => sendLink(user.id),
                          t('admin.linkSent', { email: user.email }),
                        )}
                      title={t('admin.sendLink')}
                      aria-label={t('admin.sendLink')}
                    >
                      <Mail size={16} />
                    </button>
                  {/if}
                  {#if !me}
                    <button
                      class="icon"
                      disabled={busyId === user.id}
                      onclick={() =>
                        void act(user, () => updateUser(user.id, { is_admin: !user.is_admin }))}
                      title={user.is_admin ? t('admin.removeAdmin') : t('admin.makeAdmin')}
                      aria-label={user.is_admin ? t('admin.removeAdmin') : t('admin.makeAdmin')}
                    >
                      {#if user.is_admin}<ShieldOff size={16} />{:else}<Shield size={16} />{/if}
                    </button>
                    <button
                      class="icon"
                      disabled={busyId === user.id}
                      onclick={() => toggleActive(user)}
                      title={user.is_active ? t('admin.disable') : t('admin.enable')}
                      aria-label={user.is_active ? t('admin.disable') : t('admin.enable')}
                    >
                      {#if user.is_active}<UserX size={16} />{:else}<UserCheck size={16} />{/if}
                    </button>
                  {/if}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</section>

{#if adding}
  <AddPeople onclose={() => (adding = false)} onadded={() => void load()} />
{/if}

<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h1 {
    font-size: var(--text-2xl);
    font-weight: 600;
    color: var(--color-text);
  }

  .card {
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
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

  tr:last-child td {
    border-bottom: none;
  }

  tr.disabled td {
    color: var(--color-text-muted);
  }

  .email {
    color: var(--color-text-muted);
  }

  .badge {
    margin-left: var(--space-2);
    padding: 1px 6px;
    border: 1px solid var(--color-accent);
    border-radius: var(--radius-sm);
    color: var(--color-accent);
    font-size: var(--text-xs);
  }

  .status {
    font-size: var(--text-xs);
  }

  .status.active {
    color: var(--color-success);
  }

  .status.invited,
  .status.unverified {
    color: var(--color-warning);
  }

  .status.disabled {
    color: var(--color-text-muted);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-1);
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

  .icon:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -2px;
  }

  .icon:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .muted {
    padding: var(--space-1);
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

  /* A phone has no room for the address column; the name is enough. */
  @media (max-width: 720px) {
    .email {
      display: none;
    }
  }
</style>
