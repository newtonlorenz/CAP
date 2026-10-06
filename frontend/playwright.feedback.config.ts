import { defineConfig, devices } from '@playwright/test'

if (!process.env.PAGE_FEEDBACK_REPO) throw new Error('Set PAGE_FEEDBACK_REPO to the standalone repository')

export default defineConfig({
  testDir: './e2e-feedback',
  workers: 1,
  timeout: 45_000,
  use: { baseURL: 'http://127.0.0.1:18193', trace: 'retain-on-failure', channel: process.env.PLAYWRIGHT_CHANNEL || 'chromium' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: '../backend/.venv/bin/python ../scripts/feedback-e2e-server.py "$PAGE_FEEDBACK_REPO"',
      url: 'http://127.0.0.1:18192/api/v1/health', reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 18193 --strictPort',
      env: { VITE_API_PROXY_TARGET: 'http://127.0.0.1:18192' },
      url: 'http://127.0.0.1:18193', reuseExistingServer: false,
    },
  ],
})
