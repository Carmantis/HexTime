<script lang="ts">
  import type { Snippet } from 'svelte';

  type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

  interface Props {
    variant?: Variant;
    type?: 'button' | 'submit';
    disabled?: boolean;
    title?: string;
    onclick?: () => void;
    children: Snippet;
  }

  let {
    variant = 'secondary',
    type = 'button',
    disabled = false,
    title,
    onclick,
    children,
  }: Props = $props();
</script>

<button class="btn {variant}" {type} {disabled} {title} {onclick}>
  {@render children()}
</button>

<style>
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    padding: 6px 14px;
    border-radius: var(--radius-sm);
    border: 1px solid transparent;
    font-size: var(--text-sm);
    font-weight: 500;
    cursor: pointer;
    transition:
      background-color 0.15s ease,
      color 0.15s ease,
      opacity 0.15s ease;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .btn:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }

  .primary {
    background-color: var(--color-accent);
    color: var(--color-on-accent);
    font-weight: 600;
  }

  .primary:hover:not(:disabled) {
    opacity: 0.9;
  }

  .secondary {
    background: none;
    border-color: var(--color-border);
    color: var(--color-text);
  }

  .secondary:hover:not(:disabled) {
    background-color: var(--color-surface-hover);
  }

  .ghost {
    background: none;
    color: var(--color-text-muted);
  }

  .ghost:hover:not(:disabled) {
    background-color: var(--color-surface-hover);
    color: var(--color-text);
  }

  .danger {
    background: none;
    border-color: var(--color-border);
    color: var(--color-error);
  }

  .danger:hover:not(:disabled) {
    background-color: color-mix(in srgb, var(--color-error) 12%, transparent);
  }
</style>
