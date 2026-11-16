<script lang="ts">
  import { updateMe } from '$lib/api/auth';
  import { ApiError } from '$lib/api/client';
  import type { MeUpdate } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import { LOCALES, locale, t, type Locale } from '$lib/i18n/index.svelte';
  import { appConfig } from '$lib/stores/config.svelte';
  import { session, updateUser } from '$lib/stores/session.svelte';
  import { theme, type Theme } from '$lib/stores/theme.svelte';

  const THEMES: { value: Theme; key: string }[] = [
    { value: 'dark', key: 'settings.themeDark' },
    { value: 'light', key: 'settings.themeLight' },
  ];

  const LANGUAGE_NAMES: Record<Locale, string> = { fi: 'Suomi', en: 'English' };

  let name = $state(session.user?.display_name ?? '');
  let saving = $state(false);
  let saved = $state(false);
  let errorCode = $state<string | null>(null);

  /**
   * In server mode the account remembers the choices, so they follow the
   * user to another device and emails and PDFs come in their language. The
   * desktop app keeps them in the window's own storage.
   */
  async function remember(changes: MeUpdate): Promise<void> {
    if (!appConfig.isServer) return;
    try {
      updateUser(await updateMe(changes));
    } catch {
      // The choice still applies on this device; nothing to show.
    }
  }

  function chooseTheme(value: Theme): void {
    theme.current = value;
    void remember({ theme: value });
  }

  function chooseLocale(value: Locale): void {
    locale.current = value;
    void remember({ locale: value });
  }

  async function saveName(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    saving = true;
    saved = false;
    errorCode = null;
    try {
      updateUser(await updateMe({ display_name: name }));
      saved = true;
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    } finally {
      saving = false;
    }
  }
</script>

<section class="view">
  <h1>{t('settings.title')}</h1>

  {#if appConfig.isServer && session.user}
    <form class="card" onsubmit={saveName}>
      <fieldset class="group">
        <legend>{t('settings.profile')}</legend>
        <label class="field">
          <span>{t('auth.name')}</span>
          <input type="text" bind:value={name} maxlength="200" required />
        </label>
        <p class="value">{t('auth.email')}: {session.user.email}</p>
        {#if errorCode}
          <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
        {/if}
        <div class="actions">
          <Button variant="primary" type="submit" disabled={saving}>{t('settings.save')}</Button>
          {#if saved}
            <span class="value" role="status">{t('settings.profileSaved')}</span>
          {/if}
        </div>
      </fieldset>
    </form>
  {/if}

  <div class="card">
    <fieldset class="group">
      <legend>{t('settings.theme')}</legend>
      <div class="choices">
        {#each THEMES as option (option.value)}
          <button
            class="choice"
            class:active={theme.current === option.value}
            onclick={() => chooseTheme(option.value)}
            aria-pressed={theme.current === option.value}
          >
            {t(option.key)}
          </button>
        {/each}
      </div>
    </fieldset>

    <fieldset class="group">
      <legend>{t('settings.language')}</legend>
      <div class="choices">
        {#each LOCALES as code (code)}
          <button
            class="choice"
            class:active={locale.current === code}
            onclick={() => chooseLocale(code)}
            aria-pressed={locale.current === code}
          >
            {LANGUAGE_NAMES[code]}
          </button>
        {/each}
      </div>
    </fieldset>

    <fieldset class="group">
      <legend>{t('settings.mode')}</legend>
      <p class="value">{appConfig.current?.mode ?? t('common.loading')}</p>
    </fieldset>
  </div>
</section>

<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5);
  }

  h1 {
    font-size: var(--text-2xl);
    font-weight: 600;
    color: var(--color-text);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-5);
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    max-width: 520px;
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    border: none;
  }

  legend {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--color-text);
    padding: 0;
    margin-bottom: var(--space-2);
  }

  .choices {
    display: flex;
    gap: var(--space-2);
  }

  .choice {
    padding: 6px 16px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    cursor: pointer;
    transition:
      background-color 0.15s ease,
      color 0.15s ease;
  }

  .choice:hover:not(.active) {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  .choice.active {
    background-color: color-mix(in srgb, var(--color-accent) 15%, transparent);
    border-color: var(--color-accent);
    color: var(--color-accent);
    font-weight: 600;
  }

  .value {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
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

  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .error {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
    color: var(--color-error);
    font-size: var(--text-sm);
  }
</style>
