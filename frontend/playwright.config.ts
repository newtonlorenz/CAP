import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  // Tour coverage owns a synthetic API fixture and a separate Vite server.
  testIgnore: '**/*product_tour*.spec.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : [['list'], ['html', { open: 'never' }]],
  globalSetup: './e2e/global-setup.ts',
  use: {
    // Force IPv4; some environments disallow binding to ::1.
    baseURL: 'http://127.0.0.1:15173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 15173',
    url: 'http://127.0.0.1:15173',
    reuseExistingServer: process.env.CAP_PILOT_REUSE_SERVER === '1',
  },
})
