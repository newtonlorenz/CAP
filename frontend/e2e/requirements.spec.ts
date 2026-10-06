import { test, expect } from '@playwright/test'
import { loginAsAdmin } from './testCredentials'

const openApprovedRequirementsSetRaw = async (page: any) => {
  await page.goto('/requirements')
  await page.getByRole('heading', { name: /^Requirements$/i }).waitFor()

  await page.waitForFunction(() => {
    const hasRows = document.querySelectorAll('table tbody tr').length > 0
    const hasCards =
      document.querySelectorAll('[data-testid="requirements-sets-mobile-cards"] > *').length > 0
    const hasEmpty = (document.body.textContent || '').includes('No requirement sets available.')
    return hasRows || hasCards || hasEmpty
  })

  const hasEmptyState = await page
    .getByText('No requirement sets available.', { exact: false })
    .count()
  if (hasEmptyState > 0) {
    throw new Error('No requirement sets available to open (E2E seed missing?)')
  }

  // Desktop: the set name is the primary link. Mobile: an "Open <name>" link still exists.
  const preferredOpenLink = page.getByRole('link', { name: /^Open\s+E2E Document/i }).first()
  if ((await preferredOpenLink.count()) > 0) {
    await preferredOpenLink.click()
    await page.waitForURL(/\/requirements\/sets\//)
    return
  }

  const preferredSetLink = page.getByRole('link', { name: /E2E Document/i }).first()
  if ((await preferredSetLink.count()) > 0) {
    await preferredSetLink.click()
    await page.waitForURL(/\/requirements\/sets\//)
    return
  }

  const approvedRow = page.locator('table:visible tbody tr', { hasText: /approved/i }).first()
  if ((await approvedRow.count()) > 0) {
    await approvedRow.locator('a').first().click()
    await page.waitForURL(/\/requirements\/sets\//)
    return
  }

  const anySetLink = page.locator('table:visible tbody tr a:visible').first()
  if ((await anySetLink.count()) > 0) {
    await anySetLink.click()
    await page.waitForURL(/\/requirements\/sets\//)
    return
  }

  await page.getByRole('link', { name: /^Import\s+/i }).first().click()
  await page.waitForURL(/\/requirements\/sets\//)
}

const openEditRequirementsSet = async (page: any) => {
  await page.goto('/requirements')
  await page.getByRole('heading', { name: /^Requirements$/i }).waitFor()

  await page.waitForFunction(() => {
    const hasRows = document.querySelectorAll('table tbody tr').length > 0
    const hasCards =
      document.querySelectorAll('[data-testid="requirements-sets-mobile-cards"] > *').length > 0
    const hasEmpty = (document.body.textContent || '').includes('No requirement sets available.')
    return hasRows || hasCards || hasEmpty
  })

  const hasEmptyState = await page
    .getByText('No requirement sets available.', { exact: false })
    .count()
  if (hasEmptyState > 0) {
    throw new Error('No requirement sets available to edit (E2E seed missing?)')
  }

  // Edit is now in the row actions menu.
  const preferredRow = page.locator('table:visible tbody tr', { hasText: 'E2E Document' }).first()
  if ((await preferredRow.count()) > 0) {
    await preferredRow.getByLabel(/Actions for/i).click()
    await page.getByRole('menuitem', { name: /^Edit$/i }).click()
    await page.waitForURL(/\/requirements\/sets\/.+\/edit/)
    return
  }

  const approvedRow = page.locator('table:visible tbody tr', { hasText: /approved/i }).first()
  if ((await approvedRow.count()) > 0) {
    await approvedRow.getByLabel(/Actions for/i).click()
    await page.getByRole('menuitem', { name: /^Edit$/i }).click()
    await page.waitForURL(/\/requirements\/sets\/.+\/edit/)
    return
  }

  const anyTableActions = page.locator('table:visible').getByLabel(/Actions for/i).first()
  if ((await anyTableActions.count()) > 0) {
    await anyTableActions.click()
  } else {
    await page.locator('[aria-label^="Actions for"]:visible').first().click()
  }
  await page.getByRole('menuitem', { name: /^Edit$/i }).click()
  await page.waitForURL(/\/requirements\/sets\/.+\/edit/)
}

const openApprovedRequirementsSet = async (page: any) => {
  await openApprovedRequirementsSetRaw(page)
  const library = page.getByRole('button', { name: 'Requirement library', exact: true })
  await library.click()
}

test.describe('Requirements Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.waitForURL('/')
    await expect(page.getByLabel('Jurisdiction selector').locator('option:checked')).toHaveText('Example jurisdiction')
  })

  test('should navigate to requirements page', async ({ page }) => {
    await page.goto('/requirements')
    await expect(page).toHaveURL('/requirements')
    await expect(page.locator('h1:has-text("Requirements")')).toBeVisible()
  })

  test('keeps review status outside the source requirement view', async ({ page }) => {
    await openApprovedRequirementsSet(page)
    await expect(page.getByLabel('Requirements status filter')).toHaveCount(0)
    await expect(page.getByRole('region', { name: 'Requirement library' })).toBeVisible()
  })

  test('should search requirements', async ({ page }) => {
    await openApprovedRequirementsSet(page)
    await page.getByLabel('Requirements search').fill('no-matching-synthetic-requirement')
    await expect(page.getByText('No requirements found', { exact: true })).toBeVisible()
  })

  test('should navigate to requirement detail', async ({ page }) => {
    await openApprovedRequirementsSet(page)
    await page.locator('table:visible tbody tr').first().waitFor()
    await page.locator('table:visible a:has-text("Open")').first().click()
    await expect(page.getByRole('textbox', { name: 'Reference ID', exact: true })).toBeVisible()
  })

  test('should show the source reference in view mode', async ({ page }) => {
    await openApprovedRequirementsSet(page)
    await page.locator('table:visible tbody tr').first().waitFor()
    await expect(page.locator('table:visible')).toBeVisible()
    await expect(page.locator('table:visible tbody').getByText('REQ-001', { exact: true })).toBeVisible()
  })

  test('should allow admin to switch to edit mode', async ({ page }) => {
    await openEditRequirementsSet(page)
    await expect(page.getByRole('button', { name: 'Add Requirement' })).toBeVisible()
  })

  test('should show outline and navigate on edit page', async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 900 })
    await openEditRequirementsSet(page)

    const firstRow = page.locator('[data-testid="requirements-outline-row"]').first()
    await expect(firstRow).toBeVisible()
    const targetId = await firstRow.getAttribute('data-target-id')
    expect(targetId).toBeTruthy()

    await firstRow.click()
    await expect(page.locator(`#${targetId}:visible`).first()).toBeInViewport()
  })
})
