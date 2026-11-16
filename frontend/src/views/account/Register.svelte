<script lang="ts">
  import { register } from '$lib/api/auth';
  import { ApiError } from '$lib/api/client';
  import AuthCard from '$lib/components/AuthCard.svelte';
  import Button from '$lib/components/Button.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { appConfig } from '$lib/stores/config.svelte';

  let name = $state('');
  let email = $state('');
  let busy = $state(false);
  let sent = $state(false);
  let errorCode = $state<string | null>(null);

  const domain = $derived(appConfig.current?.allowed_email_domain ?? '');

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    errorCode = null;
    try {
      await register(email, name);
      sent = true;
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    } finally {
      busy = false;
    }
  }
</script>

<AuthCard title={t('auth.registerTitle')}>
  {#if sent}
    <p class="notice" role="status">{t('auth.registerSent')}</p>
  {:else}
    <form onsubmit={submit}>
      <label class="field">
        <span>{t('auth.name')}</span>
        <input type="text" bind:value={name} autocomplete="name" required />
      </label>
      <label class="field">
        <span>{t('auth.email')}</span>
        <input type="email" bind:value={email} autocomplete="username" required />
        {#if domain}
          <small class="hint">{t('auth.registerDomain', { domain })}</small>
        {/if}
      </label>
      {#if errorCode}
        <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
      {/if}

      <Button variant="primary" type="submit" disabled={busy}>
        {busy ? t('auth.saving') : t('auth.register')}
      </Button>
    </form>
  {/if}

  {#snippet footer()}
    <a href="#/login">{t('auth.backToLogin')}</a>
  {/snippet}
</AuthCard>
