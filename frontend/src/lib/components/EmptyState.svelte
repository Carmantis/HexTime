<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    body: string;
    /** An empty state always offers the next step when there is one. */
    action?: Snippet;
  }

  let { title, body, action }: Props = $props();
</script>

<div class="empty">
  <p class="title">{title}</p>
  <p class="body">{body}</p>
  {#if action}
    <div class="action">{@render action()}</div>
  {/if}
</div>

<style>
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-6) var(--space-4);
    text-align: center;
  }

  .title {
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--color-text);
  }

  .body {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
    max-width: 42ch;
    line-height: 1.5;
  }

  .action {
    margin-top: var(--space-2);
  }
</style>
