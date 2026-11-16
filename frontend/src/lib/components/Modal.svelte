<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    onclose: () => void;
    children: Snippet;
    footer?: Snippet;
  }

  let { title, onclose, children, footer }: Props = $props();

  function onkeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') onclose();
  }
</script>

<svelte:window {onkeydown} />

<!-- The backdrop closes on click; the panel stops the click reaching it. -->
<div
  class="backdrop"
  role="button"
  tabindex="-1"
  onclick={onclose}
  onkeydown={() => {}}
  aria-label={title}
>
  <div
    class="panel"
    role="dialog"
    aria-modal="true"
    aria-label={title}
    tabindex="-1"
    onclick={(event) => event.stopPropagation()}
    onkeydown={() => {}}
  >
    <header class="head">
      <h2>{title}</h2>
      <button class="close" onclick={onclose} aria-label="×">×</button>
    </header>

    <div class="body">
      {@render children()}
    </div>

    {#if footer}
      <footer class="foot">{@render footer()}</footer>
    {/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: rgb(0 0 0 / 0.4);
    z-index: 100;
    padding: var(--space-4);
  }

  .panel {
    display: flex;
    flex-direction: column;
    width: 460px;
    max-width: 100%;
    max-height: 90vh;
    background-color: var(--color-surface-elevated);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-modal);
    overflow: hidden;
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-4);
    border-bottom: 1px solid var(--color-border);
  }

  h2 {
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--color-text);
  }

  .close {
    width: 28px;
    height: 28px;
    border: none;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    font-size: var(--text-xl);
    line-height: 1;
    cursor: pointer;
  }

  .close:hover {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  .body {
    padding: var(--space-4);
    overflow-y: auto;
  }

  .foot {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-4);
    border-top: 1px solid var(--color-border);
  }
</style>
