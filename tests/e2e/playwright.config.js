// Browser tests for the page (tests/e2e), against the made-up league in tests/fixtures/site_fixture.py: the fixture and the
// page are built into _site/ and served from there. Chrome comes from $CHROME (CI sets it to the runner's Chrome), so
// nothing is downloaded; without $CHROME, Playwright's own Chromium is used (npx playwright install chromium).
// Run: npm run test:e2e   (screenshots of every page land in test-results/, and in the CI run's artifacts)
import {defineConfig} from '@playwright/test';

const PORT = 8137;
export default defineConfig({
  testDir: '.',
  outputDir: '../../test-results',
  timeout: 60_000,
  expect: {timeout: 10_000},
  fullyParallel: true,
  workers: process.env.CI ? 2 : undefined,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['list'], ['html', {outputFolder: '../../playwright-report', open: 'never'}]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}/`,
    launchOptions: process.env.CHROME ? {executablePath: process.env.CHROME} : {},
    serviceWorkers: 'block',
  },
  webServer: {
    command: `rm -rf _site && python3 tests/fixtures/site_fixture.py _site && python3 build.py --out=_site && python3 -m http.server ${PORT} --bind 127.0.0.1 -d _site`,
    cwd: '../..',
    url: `http://127.0.0.1:${PORT}/index.html`,
    reuseExistingServer: !process.env.CI,
    stderr: 'ignore',   // the request log
  },
});
