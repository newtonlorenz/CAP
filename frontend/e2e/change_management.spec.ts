import { test, expect, type Page } from '@playwright/test'
import { e2eAdminEmail, e2eAdminPassword } from './testCredentials'

async function login(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.fill('input[type="email"]', email)
  await page.fill('input[type="password"]', password)
  await page.click('button[type="submit"]')
  await page.waitForURL('/')
  await page.getByLabel('Jurisdiction selector').selectOption({ label: 'Example jurisdiction' })
}

test.use({timezoneId:'UTC'})
test.describe('Change Management', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, e2eAdminEmail, e2eAdminPassword)
    await page.waitForURL('/')
    await expect(page.getByLabel('Jurisdiction selector').locator('option:checked')).toHaveText('Example jurisdiction')
  })

  test('opens change management workspace and tabs', async ({ page }) => {
    await page.goto('/change-management')
    await expect(page).toHaveURL('/change-management')
    await expect(page.getByRole('heading', { name: /change management/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /components/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /change register/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /baselines/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /reports/i })).toBeVisible()
  })

  test('manager happy path across register, changes, baselines, and reports', async ({ page }) => {
    const loaded=page.waitForResponse(response=>response.url().includes('/change-management/registers?') && response.request().method()==='GET')
    await page.goto('/change-management')
    await loaded

    const registerSelect = page.getByLabel('Component Register', { exact: true })
    await expect(registerSelect).toBeVisible()

    const registerOptionValues = await registerSelect
      .locator('option')
      .evaluateAll((options) => options.map((opt) => ({ value: opt.getAttribute('value') ?? '', text: opt.textContent ?? '' })))

    const existingRegister = registerOptionValues.find((opt) => opt.value)
    if (!existingRegister) {
      const registerName = `E2E Register ${Date.now()}`
      await page.getByRole('button', { name: /create register/i }).click()
      await page.getByPlaceholder('Register name').fill(registerName)
      await page.getByRole('button', { name: /save register/i }).click()
      await expect(registerSelect.locator('option')).toHaveCount(2)
    }

    const updatedRegisterOptions = await registerSelect
      .locator('option')
      .evaluateAll((options) => options.map((opt) => opt.getAttribute('value') ?? ''))
    const selectedRegister = updatedRegisterOptions.find((value) => value)
    if (selectedRegister) {
      await registerSelect.selectOption(selectedRegister)
    }

    await page.getByRole('button',{name:'Components',exact:true}).click()
    await page.locator('summary', { hasText: /^Add Component$/ }).click()
    const uid = `E2E-COMP-${Date.now()}`
    await page.getByPlaceholder('Component UID').fill(uid)
    await page.getByPlaceholder('Version').fill('1.0.0')
    await page.getByPlaceholder('Definition').fill('E2E component definition')
    await page.getByPlaceholder('Identifying characteristics').fill('e2e-characteristics')
    await page.getByRole('button', { name: /add component/i }).click()

    await expect(page.getByText(uid)).toBeVisible()

    await page.getByRole('button', { name: /change register/i }).click()

    await page.getByRole('button', { name: 'New change', exact: true }).click()
    const editor = page.getByRole('dialog', { name: 'New change' })
    const changeTitle = `E2E Change ${Date.now()}`
    await editor.getByLabel('Change title', { exact: true }).fill(changeTitle)
    await editor.getByLabel('Description', { exact: true }).fill('Change description for e2e coverage')
    await editor.locator('summary', { hasText: /^Affected components and documentation/ }).click()
    await editor.getByLabel('Category', { exact: true }).fill('operations')
    await editor.getByRole('checkbox', { name: new RegExp(uid) }).check()
    await editor.getByLabel(`Planned version for ${uid}`).fill('1.1.0')
    await editor.locator('summary', { hasText: /^Planning and justification/ }).click()
    await editor.getByLabel('Complexity', { exact: true }).fill('Low')
    await editor.getByLabel('Resource assessment', { exact: true }).fill('1 engineer')
    await editor.getByLabel('Scheduling assessment', { exact: true }).fill('next maintenance window')
    await editor.getByLabel('Planned Start', { exact: true }).fill(new Date(Date.now() + 3600000).toISOString().slice(0, 16))
    await editor.getByLabel('Planned End', { exact: true }).fill(new Date(Date.now() + 7200000).toISOString().slice(0, 16))
    await editor.getByLabel('Justification', { exact: true }).fill('Routine lifecycle update')
    await editor.locator('summary', { hasText: /^Impact evaluation/ }).click()
    await editor.getByLabel('Evaluation: expected effect', { exact: true }).fill('No downtime expected')
    await editor.getByLabel('Evaluation: risk', { exact: true }).fill('Low')
    await editor.getByLabel('Evaluation: regulatory impact', { exact: true }).fill('None')
    await editor.getByLabel('Evaluation: CIAA impact', { exact: true }).fill('No negative impact')
    await editor.locator('summary', { hasText: /^Testing organization/ }).click()
    await editor.getByLabel('Testing organization status').selectOption('pending')
    await editor.getByLabel('Testing cycle', { exact: true }).selectOption('annual')
    await editor.getByLabel('Next testing due date').fill(new Date(Date.now() + 365 * 86400000).toISOString().slice(0, 16))
    await editor.getByRole('button', { name: 'Save draft', exact: true }).click()

    const changeRow = page.getByRole('list', { name: 'Changes' }).locator('li', { hasText: changeTitle })
    await expect(changeRow).toBeVisible()
    await changeRow.getByRole('button', { name: 'Details' }).click()
    await page.getByRole('button', { name: 'Approve', exact: true }).click()
    const approval = page.getByRole('dialog', { name: `Approve: ${changeTitle}` })
    await approval.getByPlaceholder('Enter required rationale').fill('CAB approval rationale')
    const approvalResponse = page.waitForResponse(response => response.url().endsWith('/approve') && response.request().method() === 'POST')
    await approval.getByRole('button', { name: 'Approve Change', exact: true }).click()
    const approvedResponse = await approvalResponse
    expect(approvedResponse.ok(), await approvedResponse.text()).toBeTruthy()
    const approved = await approvedResponse.json()
    await expect(changeRow.getByText('Approved', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: 'Record implementation', exact: true }).click()
    const implementation = page.getByRole('dialog', { name: `Implement: ${changeTitle}` })
    await expect(implementation.getByLabel('Implemented Start')).toHaveValue('')
    await expect(implementation.getByLabel('Implemented End')).toHaveValue('')
    await implementation.getByPlaceholder('Enter required rationale').fill('Implementation rationale')
    await expect.poll(() => Math.floor(Date.now() / 1000) * 1000).toBeGreaterThan(new Date(approved.approved_at).getTime())
    const actualStamp = new Date(Math.floor(Date.now() / 1000) * 1000).toISOString().slice(0, 19)
    await implementation.getByLabel('Implemented Start').fill(actualStamp)
    await implementation.getByLabel('Implemented End').fill(actualStamp)
    await implementation.getByLabel(/actual version/).fill('1.1.0')
    await implementation.getByRole('button', { name: 'Implement Change', exact: true }).click()
    await expect(changeRow.getByText('Implemented', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: 'Verify', exact: true }).click()
    const verification = page.getByRole('dialog', { name: `Verify: ${changeTitle}` })
    await verification.getByPlaceholder('Enter required rationale').fill('Verification rationale')
    await verification.getByRole('button', { name: 'Verify Change', exact: true }).click()
    await expect(changeRow.getByText('Verified', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: /baselines/i }).click()
    const baselineLabel = `E2E Baseline ${Date.now()}`
    await page.getByPlaceholder('Baseline label').fill(baselineLabel)
    await page.getByRole('button', { name: /freeze baseline/i }).click()
    await expect(page.getByText(baselineLabel)).toBeVisible()

    await page.getByRole('button', { name: /reports/i }).click()
    await expect(page.getByText(/Change reports/i)).toBeVisible()

    const [componentsDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Download components',exact:true }).click(),
    ])
    expect(componentsDownload.suggestedFilename()).toContain('change-management-components')

    await page.locator('select').last().selectOption({ label: uid })
    const [historyDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: /component history/i }).click(),
    ])
    expect(historyDownload.suggestedFilename()).toContain('change-management-component-history')
  })

  test('non-manager cannot create registers', async ({ page }) => {
    await page.getByRole('button', { name: 'Profile options' }).click()
    await page.getByRole('button', { name: 'Logout' }).click()
    await login(page, 'contributor@example.com', e2eAdminPassword)

    await page.waitForURL('/')

    await expect(page.getByLabel('Jurisdiction selector').locator('option:checked')).toHaveText('Example jurisdiction')
    await page.goto('/change-management')

    await expect(page.getByRole('heading', { name: /change management/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /create register/i })).toHaveCount(0)
  })
})
