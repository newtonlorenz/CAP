import { test as base } from '@playwright/test'
import { loginAsAdmin } from './testCredentials'

export const test = base.extend<{
  authenticatedPage: typeof base
}>({
  authenticatedPage: async ({ page }, use) => {
    await loginAsAdmin(page)
    await page.waitForURL('/dashboard')
    await use(base)
  },
})

export { expect } from '@playwright/test'
