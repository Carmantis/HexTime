<script lang="ts">
  /**
   * Where the links in invitation and password-reset emails open.
   *
   * The link is checked first, so the person is greeted by name, or told at
   * once that the link has expired, before typing a password.
   */
  import { inspectToken, setPassword } from '$lib/api/auth';
  import { ApiError } from '$lib/api/client';
  import type { TokenInfo } from '$lib/api/types';
  import AuthCard from '$lib/components/AuthCard.svelte';
  import Button from '$lib/components/Button.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { navigate, router } from '$lib/stores/router.svelte';
  import { signedIn } from '$lib/stores/session.svelte';

  const token = router.params.get('token') ?? '';

  let info = $state<TokenInfo | null>(null);
  let invalid = $state(false);
  let password = $state('');
  let again = $state('');
  let busy = $state(false);
  let errorCode = $state<string | null>(null);
  let mismatch = $state(false);

  $effect(() => {
    inspectToken(token)
      .then((result) => (info = result))
      .catch(() => (invalid = true));
  });

  const title = $derived(
    info?.purpose === 'setup'
      ? t('auth.setupTitle', { name: info.display_name })
      : t('auth.resetTitle'),
  );
  const body = $derived(
    info
      ? t(info.purpose === 'setup' ? 'auth.setupBody' : 'auth.resetBody', {
          email: info.email ?? '',
        })
      : undefined,
  );

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    mismatch = password !== again;
    if (mismatch) return;

    busy = true;
    errorCode = null;
    try {
      signedIn(await setPassword(token, password));
      // Drop the token from the address bar: it is used up anyway.
      navigate('tracking');
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
      invalid = errorCode === 'invalid_token';
    } finally {
      busy = false;
    }
  }
</script>

{#if invalid}
  <AuthCard title={t('auth.linkInvalidTitle')} body={t('auth.linkInvalidBody')}>
    {#snippet footer()}
      <a href="#/forgot-password">{t('auth.askNewLink')}</a>
      <a href="#/login">{t('auth.backToLogin')}</a>
    {/snippet}
  </AuthCard>
{:else if !info}
  <AuthCard title={t('auth.checkingLink')} />
{:else}
  <AuthCard {title} {body}>
    <form onsubmit={submit}>
      <!-- For password managers: which account this password belongs to. -->
      <input type="email" value={info.email} autocomplete="username" hidden readonly />
      <label class="field">
        <span>{t('auth.password')}</span>
        <input type="password" bind:value={password} autocomplete="new-password" minlength="12" required />
        <small class="hint">{t('auth.passwordHint')}</small>
      </label>
      <label class="field">
        <span>{t('auth.passwordAgain')}</span>
        <input type="password" bind:value={again} autocomplete="new-password" required />
      </label>

      {#if mismatch}
        <p class="error" role="alert">{t('auth.passwordsDiffer')}</p>
      {:else if errorCode}
        <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
      {/if}

      <Button variant="primary" type="submit" disabled={busy}>
        {busy ? t('auth.saving') : t('auth.savePassword')}
      </Button>
    </form>
  </AuthCard>
{/if}
