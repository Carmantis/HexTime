<script lang="ts">
  /**
   * Asks the signed-in user about each team invitation waiting for them:
   * "Do you want to join team X?". Nobody is put in a team without a yes.
   *
   * Checked when the app opens and again whenever the window gets focus, so
   * an invitation sent while the app was open shows up without a reload.
   * "Later" hides the question until the next check.
   */
  import { ApiError } from '$lib/api/client';
  import { answerInvitation, fetchMyInvitations } from '$lib/api/teams';
  import type { MyInvitation } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import { t } from '$lib/i18n/index.svelte';

  interface Props {
    /** After joining, so an open Teams view can reload. */
    onjoined?: () => void;
  }

  let { onjoined }: Props = $props();

  let pending = $state<MyInvitation[]>([]);
  /** Asked about already and put off with "later", until the next check. */
  let later = $state<string[]>([]);
  let busy = $state(false);
  let errorCode = $state<string | null>(null);

  const current = $derived(pending.find((invitation) => !later.includes(invitation.team_id)));

  async function check(): Promise<void> {
    try {
      pending = await fetchMyInvitations();
      later = [];
    } catch {
      // Not worth an error on screen: the next focus tries again.
    }
  }

  $effect(() => {
    void check();
    const onfocus = (): void => void check();
    window.addEventListener('focus', onfocus);
    return () => window.removeEventListener('focus', onfocus);
  });

  async function answer(invitation: MyInvitation, accept: boolean): Promise<void> {
    busy = true;
    errorCode = null;
    try {
      await answerInvitation(invitation.team_id, accept);
      pending = pending.filter((other) => other.team_id !== invitation.team_id);
      if (accept) onjoined?.();
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
      // Cancelled meanwhile, say: fetch what is really waiting.
      await check();
    } finally {
      busy = false;
    }
  }
</script>

{#if current}
  {@const invitation = current}
  <Modal
    title={t('teams.joinTitle')}
    onclose={() => (later = [...later, invitation.team_id])}
  >
    <p class="question">{t('teams.joinQuestion', { team: invitation.team_name })}</p>
    {#if invitation.invited_by}
      <p class="who">{t('teams.invitedBy', { name: invitation.invited_by })}</p>
    {/if}
    <p class="who">{t('teams.joinHelp')}</p>
    {#if errorCode}
      <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
    {/if}
    {#snippet footer()}
      <Button variant="ghost" onclick={() => (later = [...later, invitation.team_id])}>
        {t('teams.later')}
      </Button>
      <Button onclick={() => void answer(invitation, false)} disabled={busy}>
        {t('teams.decline')}
      </Button>
      <Button variant="primary" onclick={() => void answer(invitation, true)} disabled={busy}>
        {t('teams.join')}
      </Button>
    {/snippet}
  </Modal>
{/if}

<style>
  .question {
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: 500;
  }

  .who {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.5;
  }

  .error {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
    color: var(--color-error);
    font-size: var(--text-sm);
  }
</style>
