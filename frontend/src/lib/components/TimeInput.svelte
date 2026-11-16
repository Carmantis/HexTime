<script lang="ts">
  import { untrack } from 'svelte';

  import { normalizeTime } from '$lib/format';
  import { t } from '$lib/i18n/index.svelte';

  interface Props {
    /** "HH:MM" on a 24-hour clock, or '' while the field holds no valid time. */
    value: string;
    required?: boolean;
  }

  let { value = $bindable(), required = false }: Props = $props();

  /*
   * A text field instead of <input type="time">: the browser draws that one in
   * the operating system's format, which is AM/PM on an English system, and a
   * page cannot change it. This one is always 24-hour.
   */
  let text = $state(untrack(() => value));
  /** The last value this field gave out, to tell it from a new one from outside. */
  let given = untrack(() => value);
  let input: HTMLInputElement;

  // A new value from outside (another entry, a default) replaces what is shown;
  // the field's own answer to what is being typed does not.
  $effect(() => {
    if (value !== given) {
      given = value;
      text = value;
    }
  });

  function onInput(): void {
    const time = normalizeTime(text);
    given = value = time ?? '';
    const empty = !text.trim();
    input.setCustomValidity(time || (empty && !required) ? '' : t('entry.invalidTime'));
  }
</script>

<input
  bind:this={input}
  type="text"
  inputmode="numeric"
  autocomplete="off"
  maxlength="5"
  placeholder={t('entry.timePlaceholder')}
  {required}
  bind:value={text}
  oninput={onInput}
  onblur={() => {
    // Show what was understood: "930" becomes "09:30".
    if (value) text = value;
  }}
/>

<style>
  input {
    width: 100%;
    padding: 7px 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: var(--text-sm);
    font-variant-numeric: tabular-nums;
  }

  input:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -1px;
  }
</style>
