<script lang="ts">
  import { onMount } from 'svelte';

  import InvitationPrompt from '$lib/components/InvitationPrompt.svelte';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import TimerBar from '$lib/components/TimerBar.svelte';
  import { locale, t } from '$lib/i18n/index.svelte';
  import { isPlainKey } from '$lib/keyboard';
  import { appConfig, loadConfig } from '$lib/stores/config.svelte';
  import { initRouter, navigate, router } from '$lib/stores/router.svelte';
  import { refreshPicker } from '$lib/stores/picker.svelte';
  import { loadSession, session } from '$lib/stores/session.svelte';
  import { theme } from '$lib/stores/theme.svelte';
  import { refreshTimer } from '$lib/stores/timer.svelte';

  import Admin from './views/Admin.svelte';
  import Calendar from './views/Calendar.svelte';
  import Placeholder from './views/Placeholder.svelte';
  import Projects from './views/Projects.svelte';
  import Reports from './views/Reports.svelte';
  import Settings from './views/Settings.svelte';
  import Teams from './views/Teams.svelte';
  import Tracking from './views/Tracking.svelte';
  import ForgotPassword from './views/account/ForgotPassword.svelte';
  import Login from './views/account/Login.svelte';
  import Register from './views/account/Register.svelte';
  import SetPassword from './views/account/SetPassword.svelte';
  import VerifyEmail from './views/account/VerifyEmail.svelte';

  let timerBar = $state<TimerBar | undefined>();
  /** Bumped when the user joins a team, so an open Teams view reloads. */
  let teamsVersion = $state(0);

  onMount(() => {
    const stopRouter = initRouter();
    void loadConfig();
    void loadSession();

    return stopRouter;
  });

  /**
   * What fills the window. The sign-in pages replace the whole app: shown on
   * their own routes (an emailed link opens one even for someone signed in),
   * and in place of everything else whenever nobody is signed in. In local
   * mode the one desktop user is always signed in, so they never appear.
   */
  const screen = $derived.by(() => {
    if (!session.checked) return 'starting';
    if (router.isAccountPage) return 'account';
    return session.signedIn ? 'app' : 'account';
  });

  // Signed in (at startup, or just now): fetch the running timer. Leaving a
  // sign-in page that has no business being open goes to the app.
  $effect(() => {
    if (!session.signedIn) return;
    void refreshTimer();
    // In server mode the account remembers language and theme (Settings
    // saves them), so they follow the user from one device to the next.
    if (appConfig.isServer && session.user) {
      locale.current = session.user.locale;
      theme.current = session.user.theme;
    }
    if (router.current === 'login' || router.current === 'register') navigate('tracking');
  });

  /** `S` starts and stops the timer. The shared rule lives in lib/keyboard. */
  function onKeydown(event: KeyboardEvent): void {
    if (screen !== 'app' || !isPlainKey(event, 's')) return;
    event.preventDefault();
    void timerBar?.toggle();
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if screen === 'account'}
  {#if router.current === 'set-password'}
    <SetPassword />
  {:else if router.current === 'verify-email'}
    <VerifyEmail />
  {:else if router.current === 'forgot-password'}
    <ForgotPassword />
  {:else if router.current === 'register' && appConfig.current?.allow_self_registration}
    <Register />
  {:else}
    <Login />
  {/if}
{:else if screen === 'app'}
  <div class="app" class:server={appConfig.isServer}>
    <Sidebar />

    <div class="main">
      <TimerBar bind:this={timerBar} />

      <main class="content">
        {#if router.current === 'tracking'}
          <Tracking />
        {:else if router.current === 'calendar'}
          <Calendar />
        {:else if router.current === 'projects'}
          <Projects />
        {:else if router.current === 'reports'}
          <Reports />
        {:else if router.current === 'settings'}
          <Settings />
        {:else if router.current === 'teams' && appConfig.isServer}
          {#key teamsVersion}
            <Teams />
          {/key}
        {:else if router.current === 'admin' && appConfig.isServer && session.user?.is_admin}
          <Admin />
        {:else}
          <Placeholder title={t(`nav.${router.current}`)} />
        {/if}
      </main>
    </div>
  </div>

  {#if appConfig.isServer}
    <InvitationPrompt
      onjoined={() => {
        teamsVersion += 1;
        void refreshPicker();
      }}
    />
  {/if}
{/if}

<style>
  .app {
    display: flex;
    height: 100%;
    background-color: var(--color-bg);
  }

  .main {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    /* The timer bar fits itself to this column, not to the window: the
       sidebar takes room, and HexStickyNote shows HexTime in a narrow panel */
    container: main / inline-size;
  }

  .content {
    flex: 1;
    overflow-y: auto;
  }

  /* Room for the bottom bar the sidebar becomes on a phone (server mode). */
  @media (max-width: 720px) {
    .app.server .content {
      padding-bottom: 56px;
    }
  }
</style>
