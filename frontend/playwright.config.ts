import { defineConfig, devices } from '@playwright/test';

const ci = !!process.env['CI'];

export default defineConfig({
  testDir: './e2e',
  testMatch: '*.e2e.ts',
  timeout: 60_000,
  retries: ci ? 1 : 0,
  reporter: ci ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:4300',
    permissions: ['microphone'],
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: [
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
            '--autoplay-policy=no-user-gesture-required',
          ],
        },
      },
    },
  ],
  webServer: [
    {
      command: 'uv run python -m e2e.server',
      cwd: '../backend',
      url: 'http://localhost:8100/health',
      timeout: 120_000,
    },
    {
      command: 'npx ng serve --configuration e2e --port 4300',
      url: 'http://localhost:4300',
      timeout: 180_000,
    },
  ],
});
