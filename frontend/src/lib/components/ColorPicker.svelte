<script lang="ts">
  import { SWATCHES } from '$lib/palette';

  interface Props {
    value: string;
    label: string;
    onchange: (color: string) => void;
  }

  let { value, label, onchange }: Props = $props();
</script>

<div class="swatches" role="radiogroup" aria-label={label}>
  {#each SWATCHES as color (color)}
    <button
      type="button"
      class="swatch"
      class:selected={value.toUpperCase() === color}
      style:--swatch={color}
      role="radio"
      aria-checked={value.toUpperCase() === color}
      aria-label={color}
      onclick={() => onchange(color)}
    ></button>
  {/each}
</div>

<style>
  .swatches {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .swatch {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 2px solid transparent;
    background-color: var(--swatch);
    cursor: pointer;
    transition: transform 0.15s ease;
  }

  .swatch:hover {
    transform: scale(1.1);
  }

  .swatch:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }

  /* A ring in the surface colour, then the text colour, reads in both themes. */
  .selected {
    border-color: var(--color-surface-elevated);
    box-shadow: 0 0 0 2px var(--color-text);
  }

</style>
