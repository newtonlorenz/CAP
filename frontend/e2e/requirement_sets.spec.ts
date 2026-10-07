import { test, expect } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'
import { loginAsAdmin } from './testCredentials'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const extractSetIdFromUrl = (url: string): string | null => {
  const match = url.match(/\/requirements\/sets\/([^/]+)/)
  return match?.[1] || null
}

test.describe('Requirement Sets', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.waitForURL('/')
    await expect(page.getByLabel('Jurisdiction selector').locator('option:checked')).toHaveText('Example jurisdiction')

    // Documents is intentionally deprecated in favor of Requirements.
    await expect(page.getByLabel('Documents')).toHaveCount(0)
  })

  test.afterEach(async ({ page }, testInfo) => {
    const createdSetIds = testInfo.annotations
      .filter((annotation) => annotation.type === 'created-set-id')
      .map((annotation) => annotation.description)
      .filter((value): value is string => !!value)

    if (createdSetIds.length === 0) return

    const cookies = await page.context().cookies()
    const accessTokenCookie = cookies.find((cookie) => cookie.name === 'access_token')
    if (!accessTokenCookie?.value) {
      throw new Error('Missing access_token cookie for cleanup')
    }

    const token = accessTokenCookie.value
    for (const setId of createdSetIds) {
      const response = await page.request.delete(`/api/v1/documents/${setId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const status = response.status()
      if (status !== 204 && status !== 404) {
        const body = await response.text()
        throw new Error(`Cleanup failed for set ${setId}: ${status} ${body}`)
      }
    }
  })

  test('should render Not Found for /documents', async ({ page }) => {
    await page.goto('/documents')
    await expect(page.getByRole('heading', { name: /^Page not found$/i })).toBeVisible()
    await expect(page.getByText(/is unavailable\. The link may have changed\./i)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Back to overview', exact: true })).toHaveAttribute('href', '/')
    await expect(page.getByRole('link', { name: 'Open the guide', exact: true })).toHaveAttribute('href', '/guide')
    await expect(page.getByText('/documents')).toBeVisible()
  })

  test('should open the create requirement set modal', async ({ page }) => {
    await page.goto('/requirements')
    await page.getByRole('button', { name: /create requirement set/i }).click()

    await expect(page.getByRole('dialog', { name: /create requirement set/i })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Import from PDF' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Create manually' })).toBeVisible()
  })

  test('should create a requirement set from a PDF and land on the import screen', async ({
    page,
  }, testInfo) => {
    await page.goto('/requirements')
    await page.getByRole('button', { name: /create requirement set/i }).click()
    await page.getByRole('button', { name: 'Import from PDF' }).click()

    await page.fill('input[name="name"]', 'E2E PDF Set')
    await page.getByLabel('Document category', { exact: true }).last().fill('Operator category')
    await page.selectOption('select[name="testing_frequency"]', 'one_off')
    await page.setInputFiles('input[name="file"]', path.join(__dirname, 'fixtures', 'test.pdf'))

    await page.getByRole('button', { name: /create & import/i }).click()
    await page.waitForURL(/\/requirements\/sets\/.+\/import/)
    const setId = extractSetIdFromUrl(page.url())
    if (setId) {
      testInfo.annotations.push({ type: 'created-set-id', description: setId })
    }
    await expect(page.getByRole('heading', { name: /e2e pdf set/i })).toBeVisible()
  })

  test('should create a manual set, add a requirement, submit, and approve', async ({ page }, testInfo) => {
    await page.goto('/requirements')
    await page.getByRole('button', { name: /create requirement set/i }).click()
    await page.getByRole('button', { name: 'Create manually' }).click()

    await page.fill('input[name="name"]', 'E2E Manual Set')
    await page.getByLabel('Document category', { exact: true }).last().fill('Operator category')
    await page.selectOption('select[name="testing_frequency"]', 'one_off')

    await page.getByRole('button', { name: /create draft set/i }).click()
    await page.waitForURL(/\/requirements\/sets\/.+\/edit/)
    const setId = extractSetIdFromUrl(page.url())
    if (setId) {
      testInfo.annotations.push({ type: 'created-set-id', description: setId })
    }
    await expect(page.getByRole('heading', { name: /e2e manual set/i })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add Requirement' })).toBeVisible()

    await page.getByRole('button', { name: 'Add Requirement' }).click()
    await page.locator('input[placeholder="e.g. 1.2.3"]').fill('E2E-REQ-1')
    await page.locator('button[type="submit"]', { hasText: 'Add Requirement' }).click()
    await expect(page.getByText('E2E-REQ-1')).toBeVisible()

    await page.getByRole('textbox', { name: 'Requirement text for E2E-REQ-1' }).fill('The synthetic system shall retain its test logs.')
    await page.getByRole('textbox', { name: 'Reference for E2E-REQ-1' }).focus()
    await expect(page.getByLabel('Requirement editor').getByText('Saved', { exact: true })).toBeVisible()
    const submitted = page.waitForResponse(response =>
      response.url().endsWith(`/documents/${setId}/submit`) && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Submit for Approval' }).click()
    const submitResponse = await submitted
    expect(submitResponse.ok(), await submitResponse.text()).toBeTruthy()
    expect((await submitResponse.json()).status).toBe('pending_approval')
    await expect(page.getByRole('button', { name: 'Approve' })).toBeVisible()

    await page.getByRole('button', { name: 'Approve', exact: true }).click()
    const approved = page.waitForResponse(response =>
      new URL(response.url()).pathname.endsWith(`/documents/${setId}/approve`) && response.request().method() === 'POST')
    await page.getByRole('dialog').getByRole('button', { name: 'Approve', exact: true }).click()
    const approveResponse = await approved
    expect(approveResponse.ok(), await approveResponse.text()).toBeTruthy()
    expect((await approveResponse.json()).status).toBe('approved')
    await page.waitForURL(/\/requirements\/sets\/[^/]+$/)
  })
})
