import { defineConfig, devices } from '@playwright/test';

const devServerPort = Number.parseInt(process.env.PLAYWRIGHT_PORT ?? '18080', 10);
const devServerUrl = `http://127.0.0.1:${devServerPort}`;
const webServerEnv = { ...process.env };
delete webServerEnv.NO_COLOR;
delete webServerEnv.FORCE_COLOR;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL: process.env.LIVE_BASE_URL ?? devServerUrl,
    trace: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 60_000,
  },
  webServer: process.env.LIVE_BASE_URL
    ? undefined
    : {
        command: `npm run dev -- --port ${devServerPort}`,
        env: {
          ...webServerEnv,
          POSTCSS_WORKERS: '1',
          DISABLE_POSTCSS_WORKERS: 'true',
        },
        port: devServerPort,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 1024 } },
    },
    {
      name: 'tablet',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1024, height: 768 },
        hasTouch: true,
      },
    },
    {
      name: 'mobile',
      use: { ...devices['Pixel 5'] },
    },
  ],
});
