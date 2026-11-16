<script lang="ts">
  import { ChevronLeft, ChevronRight } from '@lucide/svelte';

  import type { RangeMode } from '$lib/format';
  import { t } from '$lib/i18n/index.svelte';

  interface Props {
    mode: RangeMode;
    label: string;
    /** Which periods this view offers: day/week in the calendar,
     *  week/month/year in the reports. */
    modes: RangeMode[];
    onprev: () => void;
    onnext: () => void;
    ontoday: () => void;
    onmode: (mode: RangeMode) => void;
  }

  let { mode, label, modes, onprev, onnext, ontoday, onmode }: Props = $props();
</script>

<!-- The same toolbar as HexCalendar: ‹ › Today, the title, and a view switcher. -->
<div class="nav">
  <button class="nav-btn" onclick={onprev} aria-label={t('calendar.previous')} title="←">
    <ChevronLeft size={18} />
  </button>
  <button class="nav-btn" onclick={onnext} aria-label={t('calendar.next')} title="→">
    <ChevronRight size={18} />
  </button>
  <button class="today-btn" onclick={ontoday} title="T">{t('calendar.today')}</button>

  <h1 class="label">{label}</h1>

  <div class="switcher" role="tablist" aria-label={t('calendar.view')}>
    {#each modes as option (option)}
      <button
        role="tab"
        aria-selected={mode === option}
        class="switch-btn"
        class:active={mode === option}
        onclick={() => onmode(option)}
      >
        {t(`calendar.${option}`)}
      </button>
    {/each}
  </div>
</div>

<style>
  .nav {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: 1;
    min-width: 0;
  }

  .nav-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text);
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .nav-btn:hover,
  .today-btn:hover {
    background-color: var(--color-surface-hover);
  }

  .today-btn {
    padding: 4px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text);
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .nav-btn:focus-visible,
  .today-btn:focus-visible,
  .switch-btn:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }

  .label {
    flex: 1;
    min-width: 0;
    margin-left: var(--space-2);
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--color-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* HexCalendar's ViewSwitcher. */
  .switcher {
    display: flex;
    gap: 2px;
    padding: 2px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background-color: var(--color-surface);
  }

  .switch-btn {
    padding: 4px 14px;
    border: none;
    border-radius: calc(var(--radius-md) - 2px);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: 500;
    cursor: pointer;
    transition:
      background-color 0.15s ease,
      color 0.15s ease;
  }

  .switch-btn:hover:not(.active) {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  .switch-btn.active {
    background-color: var(--color-accent);
    color: var(--color-on-accent);
    font-weight: 600;
  }
</style>
