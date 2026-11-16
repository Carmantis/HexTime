/// <reference types="vitest/config" />
import path from 'node:path';

import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [svelte()],

  resolve: {
    alias: { $lib: path.resolve('./src/lib') },
  },

  server: {
    port: 5173,
    proxy: {
      // In development Vite serves the UI and the backend stays on :8000.
      // The app itself always uses relative URLs, so the same build works
      // unchanged inside the pywebview window and behind Caddy.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },

  // Unit tests live next to the code; e2e/ is Playwright's (npm run e2e).
  test: {
    include: ['src/**/*.test.ts'],
  },

  build: {
    // FastAPI mounts this directory and serves it as the application.
    outDir: '../backend/app/static',
    emptyOutDir: true,
  },
});
