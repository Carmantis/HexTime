<script lang="ts">
  /**
   * The frame every sign-in page shares: logo, title, an optional line of
   * text, the page's own content, and links underneath.
   */
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    body?: string;
    children?: Snippet;
    footer?: Snippet;
  }

  let { title, body, children, footer }: Props = $props();
</script>

<div class="page">
  <div class="card">
    <img class="logo" src="/favicon.svg" alt="" width="48" height="48" />
    <h1>{title}</h1>
    {#if body}
      <p class="body">{body}</p>
    {/if}
    {@render children?.()}
  </div>
  {#if footer}
    <div class="footer">{@render footer()}</div>
  {/if}
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-4);
    min-height: 100%;
    padding: var(--space-5);
    background-color: var(--color-bg);
    overflow-y: auto;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    width: min(380px, 100%);
    padding: var(--space-6) var(--space-5);
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }

  .logo {
    align-self: center;
  }

  h1 {
    font-size: var(--text-xl);
    font-weight: 600;
    color: var(--color-text);
    text-align: center;
  }

  .body {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
    text-align: center;
    line-height: 1.5;
  }

  .footer {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
    color: var(--color-text-muted);
  }

  /*
   * Form parts used by every sign-in page, styled once here. :global because
   * the markup comes from the pages through the slot.
   */
  .card :global(form) {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .card :global(.field) {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .card :global(.field > span) {
    font-size: var(--text-xs);
    font-weight: 500;
    color: var(--color-text-muted);
  }

  .card :global(input) {
    padding: 8px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  .card :global(input:focus-visible) {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }

  .card :global(.hint) {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
  }

  .card :global(.error),
  .card :global(.notice) {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    line-height: 1.5;
  }

  .card :global(.error) {
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
    color: var(--color-error);
  }

  .card :global(.notice) {
    background-color: color-mix(in srgb, var(--color-success) 12%, transparent);
    color: var(--color-text);
  }

  .card :global(.btn) {
    width: 100%;
  }

  /* Links in the footer and in pages; :global because they come from slots. */
  .page :global(a) {
    color: var(--color-accent);
    text-decoration: none;
  }

  .page :global(a:hover) {
    text-decoration: underline;
  }
</style>
