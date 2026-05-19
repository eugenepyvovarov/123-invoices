const { defineConfig, devices } = require('@playwright/test');

const host = process.env.PLAYWRIGHT_HOST || '127.0.0.1';
const port = process.env.PLAYWRIGHT_PORT || '8000';
const previewBaseURL = process.env.OPENCODE_PREVIEW_PUBLIC_URL || '';
const baseURL = previewBaseURL || process.env.PLAYWRIGHT_BASE_URL || `http://${host}:${port}`;
const testTimeout = process.env.CI ? 90_000 : 45_000;
const authStatePath = process.env.PLAYWRIGHT_AUTH_STATE_PATH || 'tmp/playwright-auth-state.json';
const outputDir = process.env.OPENCODE_DEMO_VIDEO_DIR || 'test-results';
const pythonBin = process.env.PLAYWRIGHT_PYTHON_BIN || 'python';
const videoMode = process.env.PLAYWRIGHT_VIDEO || 'retain-on-failure';
const reuseExistingServer = process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER === '1';

module.exports = defineConfig({
  testDir: './tests/e2e',
  outputDir,
  timeout: testTimeout,
  workers: process.env.CI ? 1 : undefined,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never' }]]
    : [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: videoMode,
  },
  projects: [
    {
      name: 'setup',
      testMatch: /.*\.setup\.js/,
      retries: 0,
    },
    {
      name: 'chromium',
      dependencies: ['setup'],
      testIgnore: /.*\.setup\.js/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: authStatePath,
      },
    },
  ],
  webServer: previewBaseURL ? undefined : {
    command: `${pythonBin} manage.py runserver ${host}:${port}`,
    url: baseURL,
    reuseExistingServer,
    timeout: 120_000,
    env: {
      ...process.env,
      DEBUG: process.env.DEBUG || '1',
      ALLOWED_HOSTS: process.env.ALLOWED_HOSTS || '127.0.0.1,localhost',
      DB_PATH: process.env.DB_PATH || 'db/e2e.sqlite3',
    },
  },
});
