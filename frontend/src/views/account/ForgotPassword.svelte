<script lang="ts">
  import { forgotPassword } from '$lib/api/auth';
  import { ApiError } from '$lib/api/client';
  import AuthCard from '$lib/components/AuthCard.svelte';
  import Button from '$lib/components/Button.svelte';
  import { t } from '$lib/i18n/index.svelte';

  let email = $state('');
  let busy = $state(false);
  let sent = $state(false);
  let errorCode = $state<string | null>(null);

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    busy = true;
    errorCode = null;
    try {
      await forgotPassword(email);
      // The same answer whether or not the address has an account.
      sent = true;
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    } finally {
      busy = false;
    }
  }
</script>

<AuthCard title={t('auth.forgotTitle')} body={sent ? undefined : t('auth.forgotBody')}>
  {#if sent}
    <p class="notice" role="status">{t('auth.forgotSent')}</p>
  {:else}
    <form onsubmit={submit}>
      <label class="field">
        <span>{t('auth.email')}</span>
        <input type="email" bind:value={email} autocomplete="username" required />
      </label>

      {#if errorCode}
        <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
      {/if}

      <Button variant="primary" type="submit" disabled={busy}>
        {busy ? t('auth.sending') : t('auth.sendLink')}
      </Button>
    </form>
  {/if}

  {#snippet footer()}
    <a href="#/login">{t('auth.backToLogin')}</a>
  {/snippet}
</AuthCard>
