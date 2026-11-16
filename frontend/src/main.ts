import { mount } from 'svelte';

import { initLocale } from '$lib/i18n/index.svelte';
import { initTheme } from '$lib/stores/theme.svelte';
import '$lib/theme/tokens.css';

import App from './App.svelte';

// Both run before the first paint so the window never shows the wrong theme
// or the wrong language for a frame.
initTheme();
initLocale('fi');

export default mount(App, { target: document.getElementById('app')! });
