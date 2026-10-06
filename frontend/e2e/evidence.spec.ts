import { test, expect } from '@playwright/test'
import { loginAsAdmin } from './testCredentials'

test.describe('Review evidence', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.waitForURL('/')
    await expect(page.getByLabel('Jurisdiction selector').locator('option:checked')).toHaveText('Example jurisdiction')
    const token = (await page.context().cookies()).find(cookie => cookie.name === 'access_token')?.value
    expect(token).toBeTruthy()
    const headers = { Authorization: `Bearer ${token}` }
    const jurisdictions = await (await page.request.get('/api/v1/jurisdictions?limit=1000', { headers })).json()
    const jurisdiction = jurisdictions.items.find((item: { code: string }) => item.code === 'example')
    const sets = await (await page.request.get(`/api/v1/requirements/sets?jurisdiction_id=${jurisdiction.id}&limit=1000`, { headers })).json()
    const source = sets.items.find((item: { name: string }) => item.name === 'E2E Document')
    expect(source).toBeTruthy()
    const created = await page.request.post('/api/v1/review-cycles', {
      headers,
      data: { name: `E2E evidence ${Date.now()}`, jurisdiction_id: jurisdiction.id, document_ids: [source.document_id], scope: 'documents' },
    })
    expect(created.status()).toBe(201)
    const cycle = await created.json()
    await page.goto(`/review-cycles/${cycle.id}`)
    await expect(page.getByLabel('Evidence for REQ-001', { exact: true })).toBeVisible()
  })

  test('retains evidence text after reload', async ({ page }) => {
    const input = page.getByLabel('Evidence for REQ-001', { exact: true })
    await input.fill('Synthetic evidence: the test logs were inspected.')
    const saved = page.waitForResponse(response => response.url().includes('/items/') && response.request().method() === 'PUT')
    await input.blur()
    expect((await saved).ok()).toBe(true)
    await page.reload()
    await expect(input).toHaveValue('Synthetic evidence: the test logs were inspected.')
  })

  test('retains source links in review evidence', async ({ page }) => {
    const input = page.getByLabel('Evidence for REQ-001', { exact: true })
    await input.fill('Test reference: https://example.test/evidence/001')
    const saved = page.waitForResponse(response => response.url().includes('/items/') && response.request().method() === 'PUT')
    await input.blur()
    expect((await saved).ok()).toBe(true)
    await page.reload()
    await expect(input).toHaveValue('Test reference: https://example.test/evidence/001')
  })

  test('retains an uploaded synthetic evidence file', async ({ page }) => {
    await page.getByLabel('Attach evidence for REQ-001', { exact: true }).setInputFiles({ name: 'synthetic-evidence.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic evidence only.') })
    await expect(page.getByText('synthetic-evidence.txt', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('synthetic-evidence.txt', { exact: true })).toBeVisible()
  })
})
