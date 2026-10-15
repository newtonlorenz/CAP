import { defineConfig, devices } from '@playwright/test'

// Disposable real API proof. Dedicated ports preserve unrelated developer servers.
export default defineConfig({
  testDir: './e2e',
  testMatch: ['documentation.spec.ts', 'documentation-processes.spec.ts'],
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: 'list',
  globalSetup: './e2e/global-setup.ts',
  outputDir: '/tmp/cap-documentation-browser-results',
  use: { baseURL: 'http://127.0.0.1:15191', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 15191 --strictPort',
    url: 'http://127.0.0.1:15191',
    reuseExistingServer: false,
    env: { VITE_API_PROXY_TARGET: 'http://127.0.0.1:18041' },
  },
})
