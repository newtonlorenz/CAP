import { expect, test, type APIResponse, type Locator, type Page, type TestInfo } from '@playwright/test'
import { loginAsAdmin } from './testCredentials'

type Requirement = { id: string; reference_id: string; requirement_set_version_id: string; parent_id: string | null }
type ReviewItem = { id: string; requirement: Requirement }

async function json(response: APIResponse) {
  expect(response.ok(), await response.text()).toBeTruthy()
  return response.json()
}

async function createHierarchy(page: Page, info: TestInfo) {
  const markets = await json(await page.request.get('/api/v1/jurisdictions?limit=1000'))
  const market = markets.items.find((item: { code: string }) => item.code === 'example')
  expect(market).toBeDefined()
  const document = await json(await page.request.post('/api/v1/requirements/sets', { data: {
    jurisdiction_id: market.id, name: `Synthetic outline ${info.testId}-${Date.now()}`,
    document_type: 'standard', testing_frequency: 'one_off',
  } }))
  info.annotations.push({ type: 'outline-document-id', description: document.id })
  const requirements: Record<string, Requirement> = {}
  // Explicit nonnumeric references catch accidental promotion when parents are filtered out.
  for (const [reference, parent, type, text] of [
    ['CTRL-ROOT', '', 'mandatory', 'Synthetic root control'],
    ['CTRL-BRANCH', 'CTRL-ROOT', 'recommended', 'Synthetic branch control'],
    ['CTRL-DEEP', 'CTRL-BRANCH', 'mandatory', 'Synthetic needle deep control'],
    ['INFO-ROOT', '', 'informational', 'Synthetic informational root'],
    ['INFO-BRANCH', 'INFO-ROOT', 'informational', 'Synthetic informational branch'],
    ['INFO-DEEP', 'INFO-BRANCH', 'mandatory', 'Synthetic needle deep information control'],
    ['SHALLOW', '', 'mandatory', 'Synthetic needle shallow control'],
  ]) {
    requirements[reference] = await json(await page.request.post('/api/v1/requirements', { data: {
      document_id: document.id, reference_id: reference, text, requirement_type: type,
      parent_id: parent ? requirements[parent].id : null,
    } }))
  }
  return { document, market, requirements }
}

async function createAssessment(page: Page, info: TestInfo, fixture: Awaited<ReturnType<typeof createHierarchy>>) {
  const { document, market, requirements } = fixture
  const version = requirements['CTRL-ROOT'].requirement_set_version_id
  for (const action of ['submit', 'approve']) {
    await json(await page.request.post(`/api/v1/requirements/sets/${document.id}/versions/${version}/${action}`, { data: {} }))
  }
  const cycle = await json(await page.request.post('/api/v1/review-cycles', { data: {
    name: `Synthetic outline assessment ${Date.now()}`, jurisdiction_id: market.id,
    scope: 'documents', document_ids: [document.id],
  } }))
  info.annotations.push({ type: 'outline-cycle-id', description: cycle.id })
  const detail = await json(await page.request.get(`/api/v1/review-cycles/${cycle.id}`))
  const items: Record<string, ReviewItem> = {}
  for (const item of detail.items as ReviewItem[]) {
    items[item.requirement.reference_id] = item
    if (item.requirement.reference_id.startsWith('INFO-') && item.requirement.reference_id !== 'INFO-DEEP') continue
    const blocked = ['CTRL-DEEP', 'INFO-DEEP', 'SHALLOW'].includes(item.requirement.reference_id)
    await json(await page.request.put(`/api/v1/review-cycles/${cycle.id}/items/${item.id}`, { data: {
      review_status: blocked ? 'escalated' : 'confirmed', requirement_status: blocked ? 'blocked' : 'evidenced',
      review_evidence: 'Synthetic evidence reference for outline regression',
    } }))
  }
  expect(items['CTRL-DEEP'].requirement.parent_id).toBe(items['CTRL-BRANCH'].requirement.id)
  expect(items['INFO-DEEP'].requirement.parent_id).toBe(items['INFO-BRANCH'].requirement.id)
  return { cycle, items }
}

async function outline(page: Page, mobile: boolean, source: boolean) {
  if (mobile) {
    const summary = page.locator('summary').filter({ hasText: source ? /^Browse requirement hierarchy$/ : /^Requirement outline$/ })
    const open = await summary.evaluate(node => (node.parentElement as HTMLDetailsElement).open)
    if (!open) await summary.click()
  }
  const region = page.getByRole('region', { name: 'Requirements outline', exact: true })
  await expect(region).toBeVisible()
  return region
}

async function assertDepthControl(page: Page, region: Locator, value: string) {
  const select = region.getByRole('combobox', { name: 'Show levels', exact: true })
  await expect(select).toHaveValue(value)
  await expect(select.locator('option[value="3"]')).toHaveText('3 levels')
  // There must be one control, in the outline, even with shallow or empty matches.
  await expect(page.getByRole('combobox', { name: 'Show levels', exact: true })).toHaveCount(1)
  const label = region.getByText('Show levels', { exact: true })
  const heading = region.getByText('Outline', { exact: true })
  const beforeHeading = await label.evaluate((node, headingNode) => Boolean(node.compareDocumentPosition(headingNode as Node) & Node.DOCUMENT_POSITION_FOLLOWING), await heading.elementHandle())
  expect(beforeHeading, 'Show levels precedes the Outline heading').toBeTruthy()
  return select
}

const outlineRow = (region: Locator, target: string) => region.locator(`[data-testid="requirements-outline-row"][data-target-id="${target}"]`)

test.beforeEach(async ({ page }) => {
  await loginAsAdmin(page)
  const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrf_token')
  expect(csrf).toBeDefined()
  await page.context().setExtraHTTPHeaders({ 'X-CSRF-Token': csrf!.value })
})

test.afterEach(async ({ page }, info) => {
  // Only records owned by this test are removed; the seed and other browser fixtures are retained.
  for (const [annotationType, route] of [['outline-cycle-id', 'review-cycles'], ['outline-document-id', 'documents']]) {
    for (const annotation of info.annotations.filter(entry => entry.type === annotationType)) {
      const response = await page.request.delete(`/api/v1/${route}/${annotation.description}`)
      expect([204, 404], await response.text()).toContain(response.status())
    }
  }
})

for (const theme of ['light', 'dark']) {
  for (const width of [1440, 390]) {
    test(`outline levels combine with source and assessment filters: ${theme} ${width}px`, async ({ page }, info) => {
      test.setTimeout(120000)
      const mobile = width < 1024
      await page.setViewportSize({ width, height: 950 })
      await page.evaluate(value => localStorage.setItem('cap:theme', value), theme)
      const fixture = await createHierarchy(page, info)
      const { document, requirements } = fixture

      await page.goto(`/requirements/sets/${document.id}/edit?mode=all`)
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      let region = await outline(page, mobile, true)
      let select = await assertDepthControl(page, region, 'all')
      await select.selectOption('2')
      const editor = page.getByRole('region', { name: 'Requirement editor', exact: true })
      await expect(editor.getByRole('textbox', { name: 'Requirement text for CTRL-BRANCH', exact: true })).toBeVisible()
      await expect(editor.getByRole('textbox', { name: 'Requirement text for CTRL-DEEP', exact: true })).toHaveCount(0)

      await page.getByRole('textbox', { name: 'Requirements search', exact: true }).fill('needle deep control')
      await page.getByRole('combobox', { name: 'Requirement type filter', exact: true }).selectOption('mandatory')
      await assertDepthControl(page, region, '2')
      await expect(editor.getByText(/No requirements at this depth/)).toBeVisible()
      await expect(outlineRow(region, `req-${requirements['CTRL-ROOT'].id}`)).toBeDisabled()
      await expect(outlineRow(region, `req-${requirements['CTRL-BRANCH'].id}`)).toBeDisabled()
      await region.getByRole('button', { name: /^Expand CTRL-BRANCH/ }).click()
      await expect(outlineRow(region, `req-${requirements['CTRL-DEEP'].id}`)).toBeEnabled()
      await page.getByRole('button', { name: 'Focused editing', exact: true }).click()
      await expect(editor.getByRole('textbox', { name: 'Requirement text for CTRL-DEEP', exact: true })).toBeVisible()
      await assertDepthControl(page, region, '2')
      await page.getByRole('button', { name: 'All requirements', exact: true }).click()
      await page.getByRole('textbox', { name: 'Requirements search', exact: true }).fill('SHALLOW')
      await assertDepthControl(page, region, '2')
      await expect(editor.getByRole('textbox', { name: 'Requirement text for SHALLOW', exact: true })).toBeVisible()
      await page.getByRole('textbox', { name: 'Requirements search', exact: true }).fill('no-synthetic-match')
      await assertDepthControl(page, region, '2')
      await expect(region.getByText('No outline items.', { exact: true })).toBeVisible()
      await page.getByRole('textbox', { name: 'Requirements search', exact: true }).fill('')
      await page.getByRole('combobox', { name: 'Requirement type filter', exact: true }).selectOption('')
      await assertDepthControl(page, region, '2')
      await expect(editor.getByRole('textbox', { name: 'Requirement text for CTRL-BRANCH', exact: true })).toBeVisible()
      await expect(editor.getByRole('textbox', { name: 'Requirement text for CTRL-DEEP', exact: true })).toHaveCount(0)
      await page.screenshot({ path: info.outputPath(`source-outline-${theme}-${width}.png`), fullPage: true })

      // Library search must keep the original depth after the API hierarchy is loaded.
      await page.goto(`/requirements/sets/${document.id}`)
      const library = page.getByRole('region', { name: 'Requirement library', exact: true })
      await expect(library.getByRole('combobox', { name: 'Show levels', exact: true })).toHaveValue('2')
      await page.getByRole('textbox', { name: 'Requirements search', exact: true }).fill('needle deep control')
      await expect(library.locator(`a[href="/requirements/${requirements['CTRL-DEEP'].id}"]:visible`)).toHaveCount(0)
      await library.getByRole('combobox', { name: 'Show levels', exact: true }).selectOption('all')
      await expect(library.locator(`a[href="/requirements/${requirements['CTRL-DEEP'].id}"]:visible`)).toBeVisible()
      await library.getByRole('combobox', { name: 'Show levels', exact: true }).selectOption('2')
      await page.getByRole('textbox', { name: 'Requirements search', exact: true }).fill('SHALLOW')
      await expect(library.getByRole('combobox', { name: 'Show levels', exact: true })).toHaveValue('2')
      await page.getByRole('textbox', { name: 'Requirements search', exact: true }).fill('no-synthetic-match')
      await expect(library.getByRole('combobox', { name: 'Show levels', exact: true })).toHaveValue('2')
      await expect(library.getByRole('combobox', { name: 'Show levels', exact: true }).locator('option[value="3"]')).toHaveText('3 levels')

      const { cycle, items } = await createAssessment(page, info, fixture)
      await page.goto(`/review-cycles/${cycle.id}`)
      region = await outline(page, mobile, false)
      select = await assertDepthControl(page, region, '2')
      if (mobile) await page.getByRole('button', { name: 'Filters and view options', exact: true }).click()
      await page.locator('summary').filter({ hasText: /^More filters/ }).click()
      await page.getByRole('textbox', { name: 'Search', exact: true }).fill('needle')
      await page.getByRole('combobox', { name: 'Requirement Status', exact: true }).selectOption('blocked')
      await page.getByRole('button', { name: 'Needs attention', exact: true }).click()
      await expect(page.getByRole('button', { name: 'Needs attention', exact: true })).toHaveAttribute('aria-pressed', 'true')
      const hideInformational = page.getByRole('checkbox', { name: 'Hide informational', exact: true })
      await hideInformational.click()
      await expect(hideInformational).toBeChecked()
      await assertDepthControl(page, region, '2')
      await expect(page.locator(`[id="review-item-${items['CTRL-DEEP'].id}"]`)).toHaveCount(0)
      await expect(page.locator(`[id="review-item-${items['INFO-DEEP'].id}"]`)).toHaveCount(0)
      await expect(page.locator(`[id="review-item-${items.SHALLOW.id}"]`)).toBeVisible()
      await expect(outlineRow(region, `review-item-${items['CTRL-ROOT'].id}`)).toBeDisabled()
      await expect(outlineRow(region, `review-item-${items['CTRL-BRANCH'].id}`)).toBeDisabled()
      await expect(page.getByText('0 selected of 1 visible', { exact: true })).toBeVisible()
      await page.getByRole('checkbox', { name: 'Select visible', exact: true }).check()
      await expect(page.getByText('1 selected of 1 visible', { exact: true })).toBeVisible()
      await page.getByRole('checkbox', { name: 'Select visible', exact: true }).uncheck()

      await select.selectOption('3')
      await expect(page.locator(`[id="review-item-${items['CTRL-DEEP'].id}"]`)).toBeVisible()
      await expect(page.locator(`[id="review-item-${items['INFO-DEEP'].id}"]`)).toBeVisible()
      await expect(page.getByText('0 selected of 3 visible', { exact: true })).toBeVisible()
      await page.getByRole('textbox', { name: 'Search', exact: true }).fill('SHALLOW')
      await assertDepthControl(page, region, '3')
      await page.getByRole('textbox', { name: 'Search', exact: true }).fill('no-synthetic-match')
      await assertDepthControl(page, region, '3')
      await expect(region.getByText('No outline items.', { exact: true })).toBeVisible()
      await expect(page.getByRole('checkbox', { name: 'Select visible', exact: true })).toBeDisabled()
      await page.getByRole('textbox', { name: 'Search', exact: true }).fill('needle deep control')
      await select.selectOption('1')
      await expect(page.getByText(/No requirements at this depth/)).toBeVisible()
      await page.getByRole('button', { name: 'Focus on one requirement', exact: true }).click()
      await expect(page.getByRole('combobox', { name: 'Requirement status for CTRL-DEEP', exact: true })).toBeVisible()
      expect(await page.evaluate(() => localStorage.getItem('cap:outline-levels'))).toBe('1')
      await page.getByRole('button', { name: 'Document view', exact: true }).click()
      region = await outline(page, mobile, false)
      await assertDepthControl(page, region, '1')
      await expect(page.getByText(/No requirements at this depth/)).toBeVisible()
      await select.selectOption('all')
      await expect(page.getByRole('combobox', { name: 'Requirement status for CTRL-DEEP', exact: true })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
      await page.screenshot({ path: info.outputPath(`assessment-outline-${theme}-${width}.png`), fullPage: true })
    })
  }
}
