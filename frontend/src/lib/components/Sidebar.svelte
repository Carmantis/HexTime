<script lang="ts">
  import {
    Calendar,
    ChartColumn,
    Clock,
    Folder,
    LogOut,
    PanelLeft,
    Settings,
    ShieldUser,
    Users,
  } from '@lucide/svelte';

  import { t } from '$lib/i18n/index.svelte';
  import { appConfig } from '$lib/stores/config.svelte';
  import { navigate, router, type Route } from '$lib/stores/router.svelte';
  import { session, signOut } from '$lib/stores/session.svelte';

  interface Item {
    route: Route;
    icon: typeof Clock;
    serverOnly?: boolean;
    adminOnly?: boolean;
  }

  const ITEMS: Item[] = [
    { route: 'tracking', icon: Clock },
    { route: 'calendar', icon: Calendar },
    { route: 'reports', icon: ChartColumn },
    { route: 'projects', icon: Folder },
    { route: 'teams', icon: Users, serverOnly: true },
    { route: 'admin', icon: ShieldUser, serverOnly: true, adminOnly: true },
    { route: 'settings', icon: Settings },
  ];

  let collapsed = $state(false);

  // Teams exist only when the backend says it is running as a server, and
  // the user list only for its administrators. (The backend checks too.)
  const items = $derived(
    ITEMS.filter(
      (item) =>
        (!item.serverOnly || appConfig.isServer) &&
        (!item.adminOnly || session.user?.is_admin === true),
    ),
  );
</script>

<nav class="sidebar" class:collapsed class:server={appConfig.isServer} aria-label="HexTime">
  <button
    class="toggle"
    onclick={() => (collapsed = !collapsed)}
    aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
    title={collapsed ? t('nav.expand') : t('nav.collapse')}
  >
    <PanelLeft size={18} />
  </button>

  <ul class="items">
    {#each items as item (item.route)}
      {@const Icon = item.icon}
      <li>
        <button
          class="item"
          class:active={router.current === item.route}
          onclick={() => navigate(item.route)}
          aria-current={router.current === item.route ? 'page' : undefined}
          title={collapsed ? t(`nav.${item.route}`) : undefined}
        >
          <Icon size={18} />
          {#if !collapsed}
            <span class="label">{t(`nav.${item.route}`)}</span>
          {/if}
        </button>
      </li>
    {/each}
  </ul>

  <!-- Server mode only: who is signed in, and the way out. -->
  {#if appConfig.isServer && session.user}
    <div class="account">
      {#if !collapsed}
        <span class="who" title={session.user.email ?? ''}>{session.user.display_name}</span>
      {/if}
      <button
        class="item sign-out"
        onclick={() => void signOut()}
        aria-label={t('auth.signOut')}
        title={t('auth.signOut')}
      >
        <LogOut size={18} />
      </button>
    </div>
  {/if}
</nav>

<style>
  .sidebar {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    width: 196px;
    flex-shrink: 0;
    padding: var(--space-2);
    background-color: var(--color-surface);
    border-right: 1px solid var(--color-border);
  }

  .collapsed {
    width: 52px;
  }

  .account {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-top: auto;
    padding-top: var(--space-2);
    border-top: 1px solid var(--color-border-light);
  }

  .who {
    flex: 1;
    min-width: 0;
    padding-left: var(--space-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--text-sm);
    color: var(--color-text);
  }

  /* Two classes: .item (later in this file) sets width: 100%. */
  .item.sign-out {
    width: auto;
    flex-shrink: 0;
  }

  .toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-border);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
  }

  .toggle:hover {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  .items {
    display: flex;
    flex-direction: column;
    gap: 2px;
    list-style: none;
  }

  .item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    padding: 8px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    text-align: left;
    cursor: pointer;
    transition:
      background-color 0.15s ease,
      color 0.15s ease;
  }

  .item:hover:not(.active) {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  .item:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -2px;
  }

  /* Same 15 % accent tint HexCalendar uses for an active control. */
  .active {
    background-color: color-mix(in srgb, var(--color-accent) 15%, transparent);
    border-color: var(--color-accent);
    color: var(--color-accent);
    font-weight: 600;
  }

  .label {
    white-space: nowrap;
    overflow: hidden;
  }

  /*
   * Server mode on a phone: a row of icons along the bottom instead of a
   * column on the left. (The desktop window never gets this narrow.)
   */
  @media (max-width: 720px) {
    .sidebar.server {
      position: fixed;
      inset: auto 0 0 0;
      z-index: 30;
      flex-direction: row;
      align-items: center;
      width: auto;
      height: 56px;
      padding: var(--space-1) var(--space-2);
      border-right: none;
      border-top: 1px solid var(--color-border);
    }

    .server .toggle,
    .server .label,
    .server .who {
      display: none;
    }

    .server .items {
      flex: 1;
      flex-direction: row;
      justify-content: space-around;
    }

    .server .item {
      justify-content: center;
      width: 44px;
      height: 44px;
      padding: 0;
    }

    .server .account {
      margin-top: 0;
      padding-top: 0;
      padding-left: var(--space-2);
      border-top: none;
      border-left: 1px solid var(--color-border-light);
    }
  }
</style>
