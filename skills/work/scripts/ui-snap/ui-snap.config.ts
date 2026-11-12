/**
 * ui-snap.config.ts -- before/after screenshots for the /work skill's UI layer (references/media.md).
 *
 *   UI_SNAP=before UI_SNAP_BASE=http://localhost:3000 npx playwright test -c ui-snap.config.ts   # base code, before any change
 *   UI_SNAP=after  UI_SNAP_BASE=http://localhost:3000 npx playwright test -c ui-snap.config.ts   # final code; also writes diffs
 *
 * What to capture comes from <repo>/.agent/ui/pages.json (written by the planner); see spec.ts for the format.
 * Output: <repo>/.agent/ui/{before,after,diff,marked}/<id>.png and .agent/ui/shots.json (read by the run board).
 * Chromium only, one worker, animations off: the point is a stable picture, not browser coverage.
 *
 * Env: UI_SNAP (before|after, required), UI_SNAP_BASE (app URL, required), UI_SNAP_AUTH (storageState path pattern
 * with {role}, relative to the repo, e.g. "tests/e2e/.auth/{role}.json"), UI_SNAP_REPO (default: git top level),
 * UI_SNAP_DIR (default <repo>/.agent/ui), UI_SNAP_CHANNEL (e.g. "chrome" to use the installed Chrome).
 */
import { defineConfig, devices } from '@playwright/test';

if (!process.env.UI_SNAP_BASE) throw new Error('set UI_SNAP_BASE to the app URL, e.g. http://localhost:3000');

export default defineConfig({
  testDir: '.',
  testMatch: 'ui-snap.spec.ts',
  outputDir: './test-results',
  globalSetup: './setup.ts',
  globalTeardown: './teardown.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [['list']],
  use: {
    baseURL: process.env.UI_SNAP_BASE,
    ignoreHTTPSErrors: true,
    ...devices['Desktop Chrome'],
    ...(process.env.UI_SNAP_CHANNEL ? { channel: process.env.UI_SNAP_CHANNEL } : {}),
  },
});
