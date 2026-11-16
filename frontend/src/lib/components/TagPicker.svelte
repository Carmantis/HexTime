<script lang="ts">
  import { fetchTags } from '$lib/api/tags';
  import type { Tag } from '$lib/api/types';
  import { t } from '$lib/i18n/index.svelte';

  interface Props {
    /** The ids currently chosen. The parent owns this list. */
    selected: string[];
    onchange: (ids: string[]) => void;
  }

  let { selected, onchange }: Props = $props();

  let available = $state<Tag[]>([]);

  $effect(() => {
    void fetchTags()
      .then((tags) => (available = tags))
      .catch(() => {
        // An empty picker is better than a broken form.
      });
  });

  function toggle(id: string): void {
    onchange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  }
</script>

<div class="picker" role="group" aria-label={t('entry.tags')}>
  {#if available.length === 0}
    <span class="none">{t('entry.noTags')}</span>
  {:else}
    {#each available as tag (tag.id)}
      <button
        type="button"
        class="chip"
        class:on={selected.includes(tag.id)}
        style:--tag-color={tag.color}
        onclick={() => toggle(tag.id)}
        aria-pressed={selected.includes(tag.id)}
      >
        <span class="dot"></span>
        {tag.name}
      </button>
    {/each}
  {/if}
</div>

<style>
  .picker {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .none {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 3px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    cursor: pointer;
    transition:
      background-color 0.15s ease,
      color 0.15s ease;
  }

  .chip:hover:not(.on) {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  /* Tag colour as a dot plus a light tint, never a large filled area. */
  .chip.on {
    background-color: color-mix(in srgb, var(--tag-color) 18%, transparent);
    border-color: var(--tag-color);
    color: var(--color-text);
  }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: var(--tag-color);
  }
</style>
