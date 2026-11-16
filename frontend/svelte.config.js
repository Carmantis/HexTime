import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
  compilerOptions: {
    // Runes everywhere. No legacy `export let` or `$:` reactivity.
    runes: true,
  },
};
