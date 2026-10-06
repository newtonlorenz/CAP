import { test, expect } from '@playwright/test'
import { loginAsAdmin } from './testCredentials'

test.describe('Reports', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.waitForURL('/')
    await expect(page.getByLabel('Jurisdiction selector').locator('option:checked')).toHaveText('Example jurisdiction')
  })

  test('should navigate to reports page', async ({ page }) => {
    await page.click('text=Reports')
    await expect(page).toHaveURL('/reports')
    await expect(page.locator('h1:has-text("Reports")')).toBeVisible()
  })

  test('opens assessment reports and retains the other report categories', async ({ page }) => {
    await page.click('text=Reports')
    await expect(page.getByRole('button', { name: 'Compliance overview' })).toHaveCount(0)
    await expect(page.getByRole('combobox', { name: 'Requirement assessment', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Compliance Summary' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Detailed Compliance' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Gap Analysis' })).toBeVisible()
    await page.getByRole('button', { name: 'Change management', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Components' })).toBeVisible()
    await page.getByRole('button', { name: 'Audit trail', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Audit Trail' })).toBeVisible()

    await page.goto('/reports?section=overview')
    await expect(page.getByRole('combobox', { name: 'Requirement assessment', exact: true })).toBeVisible()
  })

  test('should download audit trail with date range', async ({ page }) => {
    await page.click('text=Reports')

    await page.getByRole('button', { name: 'Audit trail', exact: true }).click()
    await page.getByLabel('Audit from date').fill('2024-01-01')
    await page.getByLabel('Audit to date').fill('2024-12-31')
    const [response] = await Promise.all([
      page.waitForResponse(resp => resp.url().includes('/api/v1/reports/audit-trail') && resp.status() === 200),
      page.getByRole('button', { name: 'Download', exact: true }).click(),
    ])
    expect(response.ok()).toBe(true)
  })
})
