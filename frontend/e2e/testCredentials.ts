import type { Page } from '@playwright/test'

export const e2eAdminEmail = process.env.E2E_ADMIN_EMAIL || 'admin@example.com'
export const e2eAdminPassword = process.env.E2E_ADMIN_PASSWORD || process.env.BOOTSTRAP_ADMIN_PASSWORD

if (!e2eAdminPassword) {
  throw new Error('Set E2E_ADMIN_PASSWORD or BOOTSTRAP_ADMIN_PASSWORD to the explicit local bootstrap admin password.')
}

export async function loginAsAdmin(page: Page) {
  await page.goto('/login')
  await page.fill('input[type="email"]', e2eAdminEmail)
  await page.fill('input[type="password"]', e2eAdminPassword)
  await page.click('button[type="submit"]')
  await page.waitForURL('/')
  const selector = page.getByLabel('Jurisdiction selector')
  const mobile = page.getByTestId('mobile-nav-toggle')
  await mobile.waitFor({ state: 'attached' })
  const inDrawer = await mobile.isVisible()
  if (inDrawer) await mobile.click()
  await (inDrawer ? page.getByTestId('mobile-nav-drawer').getByLabel('Jurisdiction selector') : selector).selectOption({ label: 'Example jurisdiction' })
  if (inDrawer) await page.getByTestId('mobile-nav-drawer').getByRole('button', { name: /close/i }).click()
}
