<script lang="ts">
  /** Where the link in a sign-up confirmation email opens. */
  import { verifyEmail } from '$lib/api/auth';
  import AuthCard from '$lib/components/AuthCard.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { router } from '$lib/stores/router.svelte';

  let status = $state<'checking' | 'done' | 'invalid'>('checking');

  $effect(() => {
    verifyEmail(router.params.get('token') ?? '')
      .then(() => (status = 'done'))
      .catch(() => (status = 'invalid'));
  });
</script>

{#if status === 'checking'}
  <AuthCard title={t('auth.checkingLink')} />
{:else if status === 'done'}
  <AuthCard title={t('auth.verifyTitle')} body={t('auth.verifyBody')}>
    {#snippet footer()}
      <a href="#/login">{t('auth.login')}</a>
    {/snippet}
  </AuthCard>
{:else}
  <AuthCard title={t('auth.linkInvalidTitle')} body={t('auth.linkInvalidBody')}>
    {#snippet footer()}
      <a href="#/login">{t('auth.backToLogin')}</a>
    {/snippet}
  </AuthCard>
{/if}
