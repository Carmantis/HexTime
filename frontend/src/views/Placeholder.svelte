<script lang="ts">
  import EmptyState from '$lib/components/EmptyState.svelte';
  import { t } from '$lib/i18n/index.svelte';

  interface Props {
    title: string;
  }

  let { title }: Props = $props();
</script>

<section class="view">
  <h1>{title}</h1>
  <div class="card">
    <EmptyState title={t('placeholder.title')} body={t('placeholder.body')} />
  </div>
</section>

<style>
  .view {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5);
  }

  h1 {
    font-size: var(--text-2xl);
    font-weight: 600;
    color: var(--color-text);
  }

  .card {
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
  }
</style>
