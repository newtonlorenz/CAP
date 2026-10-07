import { defineConfig, devices } from '@playwright/test'

// Only synthetic account/API responses are used. No database seeding or shared server.
export default defineConfig({
  testDir: './e2e',
  testMatch: ['product_tour.spec.ts', 'section_product_tours.spec.ts'],
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:18197', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 18197 --strictPort',
    url: 'http://127.0.0.1:18197',
    reuseExistingServer: false,
  },
})
