/**
 * End-to-end tests: the real app in a real browser.
 *
 *   npm run e2e
 *
 * They run against server mode, started by scripts/dev-server.sh on its own
 * port with a fresh database and the demo users every time (see
 * backend/scripts/dev_seed.py). Server mode covers the desktop flows too:
 * the views are the same, plus sign-in and teams.
 *
 * The browser is Playwright's own Chromium (`npx playwright install
 * chromium`), or the system's when PLAYWRIGHT_CHROMIUM is set to its path.
 */
import { defineConfig, devices } from '@playwright/test';

const PORT = 8765;

export default defineConfig({
  testDir: './e2e',
  // One database for all tests: they run one at a time, in a known order.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    locale: 'en-GB',
    timezoneId: 'Europe/Helsinki',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: process.env.PLAYWRIGHT_CHROMIUM
          ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM }
          : {},
      },
    },
  ],
  webServer: {
    // The UI is built by `npm run e2e` first; --reset starts from the demo data.
    // Its own database, so a run never wipes the one used by hand.
    command: `bash ../scripts/dev-server.sh --port ${PORT} --reset --no-build --data-dir ../backend/.dev-server/e2e`,
    url: `http://localhost:${PORT}/api/v1/config`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
