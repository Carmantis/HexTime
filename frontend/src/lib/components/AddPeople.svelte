<script lang="ts">
  /**
   * The administrator pastes a staff list, sees who would be added, sends,
   * and then sees what happened to each person. Nothing is sent before the
   * preview has been looked at.
   */
  import { addPeople } from '$lib/api/admin';
  import { ApiError } from '$lib/api/client';
  import type { AddOutcome, AddResult } from '$lib/api/types';
  import Button from '$lib/components/Button.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import { t } from '$lib/i18n/index.svelte';
  import { parsePeople } from '$lib/people';
  import { appConfig } from '$lib/stores/config.svelte';

  interface Props {
    onclose: () => void;
    /** Called after sending, so the list behind can reload. */
    onadded: () => void;
  }

  let { onclose, onadded }: Props = $props();

  let text = $state('');
  let busy = $state(false);
  let results = $state<AddResult[] | null>(null);
  let errorCode = $state<string | null>(null);

  const parsed = $derived(parsePeople(text));
  const domain = $derived(appConfig.current?.allowed_email_domain ?? 'example.fi');

  /**
   * What the backend will say about a row, known before sending: an address
   * outside the organisation, or the same person twice. The backend decides;
   * this only lets the administrator fix the list first.
   */
  const issues = $derived.by(() => {
    const seen = new Set<string>();
    return parsed.people.map((person): AddOutcome | null => {
      if (seen.has(person.email)) return 'duplicate';
      seen.add(person.email);
      const allowed = appConfig.current?.allowed_email_domain;
      if (allowed && !person.email.endsWith(`@${allowed.toLowerCase()}`)) return 'invalid_domain';
      return null;
    });
  });

  const OUTCOME_KEYS: Record<AddOutcome, string> = {
    invited: 'admin.outcomeInvited',
    resent: 'admin.outcomeResent',
    exists: 'admin.outcomeExists',
    invalid_domain: 'admin.outcomeInvalidDomain',
    duplicate: 'admin.outcomeDuplicate',
    email_failed: 'admin.outcomeEmailFailed',
  };
  const SENT: AddOutcome[] = ['invited', 'resent'];

  async function send(): Promise<void> {
    busy = true;
    errorCode = null;
    try {
      results = await addPeople(parsed.people);
      onadded();
    } catch (error) {
      errorCode = error instanceof ApiError ? error.code : 'unknown_error';
    } finally {
      busy = false;
    }
  }
</script>

<Modal title={t('admin.addPeople')} {onclose}>
  {#if results}
    <p class="summary">
      {t('admin.summary', {
        ok: results.filter((r) => SENT.includes(r.outcome)).length,
        total: results.length,
      })}
    </p>
    <ul class="rows">
      {#each results as result, index (index)}
        <li class:problem={!SENT.includes(result.outcome)}>
          <span class="who">{result.display_name || result.email}</span>
          <span class="email">{result.email}</span>
          <span class="outcome">{t(OUTCOME_KEYS[result.outcome])}</span>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="help">{t('admin.pasteHelp')}</p>
    <textarea
      bind:value={text}
      rows="8"
      placeholder={t('admin.pastePlaceholder', { domain })}
      aria-label={t('admin.addPeople')}
    ></textarea>

    {#if parsed.people.length > 0}
      <p class="count">{t('admin.preview', { count: parsed.people.length })}</p>
      <ul class="rows">
        {#each parsed.people as person, index (index)}
          {@const issue = issues[index]}
          <li class:problem={issue !== null}>
            <span class="who">{person.display_name || '–'}</span>
            <span class="email">{person.email}</span>
            <span class="outcome">{issue ? t(OUTCOME_KEYS[issue]) : ''}</span>
          </li>
        {/each}
      </ul>
    {/if}
    {#if parsed.skipped.length > 0}
      <p class="skipped">{t('admin.skipped', { lines: parsed.skipped.join(' · ') })}</p>
    {/if}
    {#if errorCode}
      <p class="error" role="alert">{t(`errors.${errorCode}`)}</p>
    {/if}
  {/if}

  {#snippet footer()}
    {#if results}
      <Button variant="primary" onclick={onclose}>{t('admin.done')}</Button>
    {:else}
      <Button variant="ghost" onclick={onclose}>{t('admin.close')}</Button>
      <Button
        variant="primary"
        onclick={() => void send()}
        disabled={busy || parsed.people.length === 0}
      >
        {busy ? t('admin.sendingInvites') : t('admin.send', { count: parsed.people.length })}
      </Button>
    {/if}
  {/snippet}
</Modal>

<style>
  .help,
  .count,
  .summary {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
    line-height: 1.5;
  }

  .summary {
    color: var(--color-text);
    font-weight: 600;
  }

  textarea {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    resize: vertical;
  }

  textarea:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  .rows {
    display: flex;
    flex-direction: column;
    max-height: 240px;
    overflow-y: auto;
    list-style: none;
    border: 1px solid var(--color-border-light);
    border-radius: var(--radius-sm);
  }

  .rows li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) auto;
    gap: var(--space-3);
    padding: var(--space-1) var(--space-3);
    border-bottom: 1px solid var(--color-border-light);
    font-size: var(--text-sm);
  }

  .rows li:last-child {
    border-bottom: none;
  }

  .who,
  .email {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .email {
    color: var(--color-text-muted);
  }

  .outcome {
    color: var(--color-success);
    white-space: nowrap;
  }

  .problem .outcome {
    color: var(--color-warning);
  }

  .skipped {
    font-size: var(--text-xs);
    color: var(--color-warning);
  }

  .error {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
    color: var(--color-error);
    font-size: var(--text-sm);
  }
</style>
