<script lang="ts">
  import { login } from '$lib/api/auth';
  import { ApiError } from '$lib/api/client';
  import AuthCard from '$lib/components/AuthCard.svelte';
  import Button from '$lib/components/Button.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { appConfig } from '$lib/stores/config.svelte';
  import { navigate } from '$lib/stores/router.svelte';
  import { signedIn } from '$lib/stores/session.svelte';

  let email = $state('');
  let password = $state('');
  let busy = $state(false);
  let errorCode = $state<string | null>(null);

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    errorCode = null;
    try {
      signedIn(await login(email, password));
      navigate('tracking');
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
      password = '';
    } finally {
      busy = false;
    }
  }
</script>

<AuthCard title={t('auth.loginTitle')}>
  <form onsubmit={submit}>
    <label class="field">
      <span>{t('auth.email')}</span>
      <input type="email" bind:value={email} autocomplete="username" required />
    </label>
    <label class="field">
      <span>{t('auth.password')}</span>
      <input type="password" bind:value={password} autocomplete="current-password" required />
    </label>

    {#if errorCode}
      <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
    {/if}

    <Button variant="primary" type="submit" disabled={busy}>
      {busy ? t('auth.loggingIn') : t('auth.login')}
    </Button>
  </form>

  {#snippet footer()}
    <a href="#/forgot-password">{t('auth.forgot')}</a>
    {#if appConfig.current?.allow_self_registration}
      <span>{t('auth.noAccount')} <a href="#/register">{t('auth.createAccount')}</a></span>
    {:else}
      <span>{t('auth.askAdmin')}</span>
    {/if}
  {/snippet}
</AuthCard>
