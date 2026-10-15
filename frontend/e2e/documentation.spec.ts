import { expect, test, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { loginAsAdmin } from './testCredentials'

async function post(page: Page, url: string, options: { data: unknown }) {
  const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrf_token')
  if (!csrf) throw new Error('The authenticated browser has no CSRF cookie.')
  return page.request.post(url, { ...options, headers: { 'X-CSRF-Token': csrf.value } })
}

async function seedRegister(page: Page) {
  const jurisdictions = await page.request.get('/api/v1/jurisdictions?limit=100')
  expect(jurisdictions.ok()).toBeTruthy()
  const jurisdiction = (await jurisdictions.json()).items.find((item: { code: string }) => item.code === 'example')
  const registerResponse = await post(page, '/api/v1/documentation/registers', { data: {
    name: `Synthetic governance register ${Date.now()}`, jurisdiction_id: jurisdiction.id,
    description: 'Expected documentation for the synthetic operator; evidence coverage requires a separate review.',
  } })
  expect(registerResponse.status(), await registerResponse.text()).toBe(201)
  const register = await registerResponse.json()
  const sectionResponse = await post(page, `/api/v1/documentation/registers/${register.id}/sections`, { data: { revision: register.revision, name: 'Policies' } })
  expect(sectionResponse.status(), await sectionResponse.text()).toBe(201)
  const section = await sectionResponse.json()
  const expectationResponse = await post(page, `/api/v1/documentation/registers/${register.id}/expectations`, { data: {
    section_id: section.id, required_documentation: 'Governance and outsourced service oversight', document_name: 'Supplier governance policy.docx',
    title: 'Governance and outsourced service oversight',
    description: 'Explain accountable decision making, incident escalation and oversight of outsourced services.\nInclude the responsible person, the review period and records of actions taken.',
    category: 'Governance', applicability: 'applicable',
    interpretation: 'A shared policy may cover several obligations; each scope needs its own rationale.',
    basis: 'Synthetic test basis; no real regulatory acceptance is asserted.',
    source_reference: 'SYNTHETIC-UNKNOWN-1', responsible_party: 'Compliance owner',
  } })
  expect(expectationResponse.status(), await expectationResponse.text()).toBe(201)
  const expectation = await expectationResponse.json()
  return { register, expectation, section }
}

async function seedAuditProject(page: Page, jurisdictionId: string) {
  const project = await post(page, '/api/v1/certification-projects', { data: {
    name: `Synthetic auditor project ${Date.now()}`, jurisdiction_id: jurisdictionId,
  } })
  expect(project.status(), await project.text()).toBe(201)
  const projectId = (await project.json()).id
  const template = await post(page, '/api/v1/preparation/templates', { data: {
    name: 'Synthetic auditor request template', kind: 'audit', fields: [
      { key: 'operator_policy', label: 'Provide the oversight policy', type: 'evidence' },
      { key: 'auditor_report', label: 'Auditor report for the synthetic review period', type: 'evidence' },
    ],
  } })
  expect(template.status(), await template.text()).toBe(201)
  const audit = await post(page, '/api/v1/preparation/cases', { data: {
    name: 'Synthetic auditor request form', template_id: (await template.json()).id,
    jurisdiction_id: jurisdictionId, project_id: projectId,
  } })
  expect(audit.status(), await audit.text()).toBe(201)
  return projectId
}

const columns = ['Document / record required', 'SCP reference', 'Comment/explanation', 'Document']
const tableColumns = [...columns, 'Actions']
const registerTable = (page: Page) => page.getByRole('table', { name: 'Documentation register entries', exact: true })
const sections = (page: Page) => page.getByRole('navigation', { name: 'Register sections', exact: true })
const rowNamed = (page: Page, name: string) => registerTable(page).getByRole('row').filter({ hasText: name })

function importWorkbook() {
  return execFileSync(process.env.CAP_PYTHON || 'python', ['-c', `
import io,sys
from openpyxl import Workbook
w=Workbook();s=w.active;s.title='Games'
s.append(['Document / record required','SCP reference','Comment/explanation','Document'])
s.append(['Synthetic incident record','UNKNOWN-42','','incident-log.pdf'])
s=w.create_sheet('Records');s.append(['Required record / report','DGA source and location','Comment/explanation','Document'])
s.append(['Synthetic oversight report','UNKNOWN-43','Independent review comment','oversight-report.txt'])
s=w.create_sheet('Notes and sources');s.append(['Topic / source code','Explanation / document','Version / reference'])
s.append(['SCP','Synthetic source alias only','v3'])
b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())
`])
}

for (const variant of [
  { name: 'light-desktop', theme: 'light', width: 1440, height: 1080 },
  { name: 'dark-desktop', theme: 'dark', width: 1440, height: 1080 },
  { name: 'dark-mobile', theme: 'dark', width: 390, height: 844 },
] as const) {
  test(`original register columns, Actions, and imported sections remain usable in ${variant.name}`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.setViewportSize({ width: variant.width, height: variant.height })
    await page.addInitScript(theme => localStorage.setItem('cap:theme', theme), variant.theme)
    await loginAsAdmin(page)
    const { register, expectation } = await seedRegister(page)
    await page.goto(`/library?section=documentation&register=${register.id}`)
    await expect(registerTable(page).getByRole('columnheader')).toHaveText(tableColumns, { timeout: 15_000 })
    await sections(page).getByRole('button', { name: 'Policies', exact: true }).click()
    const row = rowNamed(page, expectation.required_documentation)
    await expect(row).toBeVisible()
    await expect(row.getByRole('cell').nth(1)).toContainText('SYNTHETIC-UNKNOWN-1')
    await expect(row.getByRole('cell').nth(2)).toContainText(expectation.description)
    await expect(row.getByRole('cell').nth(3)).toContainText('Supplier governance policy.docx')
    await expect(row.getByRole('cell')).toHaveCount(5)
    for (let index = 0; index < 4; index++) await expect(row.getByRole('cell').nth(index).getByRole('button')).toHaveCount(0)
    const actions = row.getByRole('cell').last()
    for (const name of [/^Details for /, /^Edit row /, /^Assign user for /, /^Link certification review for /, /^Link document for /]) {
      await expect(actions.getByRole('button', { name })).toBeVisible()
    }
    await expect(page.getByRole('combobox', { name: 'Coverage decision', exact: true })).toHaveCount(0)
    if (variant.width < 1120) {
      const scroller = page.getByRole('region', { name: 'Scrollable documentation table', exact: true })
      expect((await registerTable(page).boundingBox())!.width).toBeGreaterThanOrEqual(1120)
      expect(await scroller.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
      await scroller.evaluate(element => { element.scrollLeft = element.scrollWidth })
      const lastHeader = (await registerTable(page).getByRole('columnheader').last().boundingBox())!
      const scrollBounds = (await scroller.boundingBox())!
      expect(lastHeader.x).toBeGreaterThanOrEqual(scrollBounds.x)
      expect(lastHeader.x + lastHeader.width).toBeLessThanOrEqual(scrollBounds.x + scrollBounds.width + 1)
      await page.screenshot({ path: `/tmp/cap-documentation-table-${variant.name}-actions.png`, fullPage: true })
      await scroller.evaluate(element => { element.scrollLeft = 0 })
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: `/tmp/cap-documentation-table-${variant.name}.png`, fullPage: true })
    await row.getByRole('button', { name: /^Details for / }).click()
    const details = page.getByRole('dialog', { name: 'Row details', exact: true })
    await expect(details.getByRole('heading', { name: 'Manual coverage review', exact: true })).toBeVisible()
    await page.screenshot({ path: `/tmp/cap-documentation-table-${variant.name}-details.png`, fullPage: true })
    await details.getByRole('button', { name: 'Close dialog', exact: true }).click()
    await page.getByRole('button', { name: 'Import spreadsheet', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Documentation spreadsheet', { exact: true }).setInputFiles({
      name: 'synthetic-register.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: importWorkbook(),
    })
    await dialog.getByRole('button', { name: 'Preview spreadsheet', exact: true }).click()
    await expect(dialog.getByRole('heading', { name: 'Synthetic incident record', exact: true })).toBeVisible()
    await dialog.getByText('Worksheet columns and source notes', { exact: true }).click()
    const bounds = await dialog.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.x).toBeGreaterThanOrEqual(-1)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(variant.width + 1)
    await page.screenshot({ path: `/tmp/cap-documentation-table-${variant.name}-import.png`, fullPage: true })
    await dialog.getByRole('checkbox', { name: /I reviewed the worksheet mappings/ }).check()
    await dialog.getByRole('button', { name: 'Confirm import', exact: true }).click()
    await expect(dialog.getByText(/Import complete. 2 created/)).toBeVisible()
    await dialog.getByRole('button', { name: 'Close', exact: true }).click()
    await sections(page).getByRole('button', { name: 'Games', exact: true }).click()
    const game = rowNamed(page, 'Synthetic incident record')
    await expect(game.getByRole('cell').nth(1)).toContainText('UNKNOWN-42')
    await expect(game.getByRole('cell').nth(2)).toHaveText(/^\s*(?:—)?\s*$/)
    await expect(game.getByRole('cell').nth(3)).toContainText('incident-log.pdf')
    await sections(page).getByRole('button', { name: 'Records', exact: true }).click()
    const record = rowNamed(page, 'Synthetic oversight report')
    await expect(record.getByRole('cell').nth(2)).toContainText('Independent review comment')
    await expect(record.getByRole('cell').nth(3)).toContainText('oversight-report.txt')
    await expect(sections(page).getByRole('button', { name: 'Notes and sources', exact: true })).toHaveCount(0)
    await page.reload()
    await sections(page).getByRole('button', { name: 'Games', exact: true }).click()
    await expect(rowNamed(page, 'Synthetic incident record')).toBeVisible()
    expect(errors).toEqual([])
  })
}

test('a four-field row conflict preserves the draft until explicit reconciliation and save', async ({ page }) => {
  await loginAsAdmin(page)
  const { register, expectation } = await seedRegister(page)
  await page.goto(`/library?section=documentation&register=${register.id}`)
  await rowNamed(page, expectation.required_documentation).getByRole('button', { name: /^Edit row / }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit row', exact: true })
  const required = dialog.getByRole('textbox', { name: columns[0], exact: true })
  await expect(required).toHaveValue(expectation.required_documentation)
  await required.fill('Unsaved governance draft')
  const save = dialog.getByRole('button', { name: 'Save row', exact: true })
  const endpoint = `**/api/v1/documentation/expectations/${expectation.id}`
  await page.route(endpoint, async route => {
    if (route.request().method() === 'PATCH') await route.fulfill({ status: 409, json: { detail: 'Synthetic conflicting edit; reload the latest version.' } })
    else await route.continue()
  })
  await save.click()
  await expect(dialog.getByText('Synthetic conflicting edit; reload the latest version.', { exact: true })).toBeVisible()
  await expect(required).toHaveValue('Unsaved governance draft')
  await page.unroute(endpoint)
  await dialog.getByRole('button', { name: 'Load current row', exact: true }).click()
  await dialog.getByRole('button', { name: 'Keep reviewed draft', exact: true }).click()
  await expect(required).toHaveValue('Unsaved governance draft')
  await save.click()
  await expect(dialog).toHaveCount(0)
  await page.reload()
  await expect(rowNamed(page, 'Unsaved governance draft')).toBeVisible()
})

test('an empty named section survives reload and its minimal row keeps advanced review and export available', async ({ page }) => {
  test.setTimeout(75_000)
  await loginAsAdmin(page)
  await page.goto('/library?section=documentation')
  await page.getByRole('button', { name: 'New register', exact: true }).click()
  await page.getByRole('textbox', { name: 'Register name', exact: true }).fill(`Manual synthetic register ${Date.now()}`)
  await page.getByRole('button', { name: 'Create register', exact: true }).click()
  await page.getByRole('button', { name: 'New section', exact: true }).click()
  await page.getByRole('textbox', { name: 'Section name', exact: true }).fill('Manual policies')
  await page.getByRole('button', { name: 'Create section', exact: true }).click()
  await sections(page).getByRole('button', { name: 'Manual policies', exact: true }).click()
  await page.reload()
  await expect(sections(page).getByRole('button', { name: 'Manual policies', exact: true })).toBeVisible()
  await sections(page).getByRole('button', { name: 'Manual policies', exact: true }).click()
  await page.getByRole('button', { name: 'Add row', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: 'Add row', exact: true })
  await expect(dialog.getByRole('textbox')).toHaveCount(4)
  await dialog.getByRole('textbox', { name: columns[0], exact: true }).fill('Manual oversight expectation')
  await dialog.getByRole('textbox', { name: columns[1], exact: true }).fill('SYNTHETIC-SOURCE-1')
  await dialog.getByRole('textbox', { name: columns[3], exact: true }).fill('Oversight policy.docx')
  await dialog.getByRole('button', { name: 'Save row', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await page.reload()
  await sections(page).getByRole('button', { name: 'Manual policies', exact: true }).click()
  const row = rowNamed(page, 'Manual oversight expectation')
  await expect(row.getByRole('cell').nth(2)).toHaveText(/^\s*(?:—)?\s*$/)
  await expect(page.getByRole('combobox', { name: 'Coverage decision', exact: true })).toHaveCount(0)
  await row.getByRole('button', { name: /^Details for / }).click()
  const details = page.getByRole('dialog', { name: 'Row details', exact: true })
  await details.getByRole('combobox', { name: 'Applicability', exact: true }).selectOption('applicable')
  await details.getByRole('button', { name: 'Save expectation', exact: true }).click()
  await details.getByRole('button', { name: 'Link obligations', exact: true }).click()
  dialog = page.getByRole('dialog', { name: 'Link obligations', exact: true })
  await dialog.getByRole('combobox', { name: 'Requirement set', exact: true }).selectOption({ label: 'E2E Document' })
  const version = dialog.getByRole('combobox', { name: 'Requirement version', exact: true })
  await expect(version.locator('option').filter({ hasText: /approved/ }).first()).toBeAttached()
  await version.selectOption({ label: await version.locator('option').filter({ hasText: /approved/ }).first().innerText() })
  await dialog.getByRole('checkbox', { name: /REQ-001/ }).check()
  await dialog.getByRole('button', { name: 'Save obligation links', exact: true }).click()
  await expect(details.getByRole('link', { name: 'REQ-001', exact: true })).toBeVisible()
  const evidenceTitle = `Manual oversight policy ${Date.now()}`
  const evidence = await post(page, '/api/v1/preparation/evidence', { data: {
    title: evidenceTitle, kind: 'note', body: 'The board reviews the synthetic service monthly.', visibility: 'organisation',
  } })
  expect(evidence.status(), await evidence.text()).toBe(201)
  await details.getByRole('button', { name: 'Link evidence', exact: true }).click()
  dialog = page.getByRole('dialog', { name: 'Link evidence', exact: true })
  await dialog.getByRole('searchbox', { name: 'Search available evidence', exact: true }).fill(evidenceTitle)
  await dialog.getByRole('checkbox', { name: new RegExp(evidenceTitle) }).check()
  await dialog.getByRole('textbox', { name: 'Evidence locator', exact: true }).fill('Section 2')
  await dialog.getByRole('textbox', { name: 'Evidence scope', exact: true }).fill('Board oversight')
  await dialog.getByRole('textbox', { name: 'Evidence period', exact: true }).fill('Current policy')
  await dialog.getByRole('textbox', { name: 'Coverage explanation', exact: true }).fill('Describes the accountable body and review cadence.')
  await dialog.getByRole('button', { name: 'Save evidence links', exact: true }).click()
  await expect(details.getByText(evidenceTitle, { exact: true })).toBeVisible()
  await details.getByRole('combobox', { name: 'Coverage decision', exact: true }).selectOption('sufficient')
  await details.getByRole('textbox', { name: 'Review rationale', exact: true }).fill('Confirmed the policy covers this exact scope and period.')
  await details.getByRole('button', { name: 'Record coverage review', exact: true }).click()
  await expect(details.getByText('Coverage review: sufficient', { exact: false })).toBeVisible()
  await details.getByRole('button', { name: 'Close dialog', exact: true }).click()
  await page.reload()
  await rowNamed(page, 'Manual oversight expectation').getByRole('button', { name: /^Details for / }).click()
  await expect(page.getByRole('dialog', { name: 'Row details', exact: true }).getByText('Coverage review: sufficient', { exact: false })).toBeVisible()
  await page.screenshot({ path: '/tmp/cap-documentation-table-manual-reviewed.png', fullPage: true })
  await page.getByRole('dialog', { name: 'Row details', exact: true }).getByRole('button', { name: 'Close dialog', exact: true }).click()
  await page.getByRole('button', { name: 'Register tools', exact: true }).click()
  await page.getByRole('button', { name: 'Prepare handover', exact: true }).click()
  dialog = page.getByRole('dialog', { name: 'Documentation handover', exact: true })
  await dialog.getByRole('searchbox', { name: 'Search handover evidence', exact: true }).fill(evidenceTitle)
  await dialog.getByRole('checkbox', { name: new RegExp(evidenceTitle) }).check()
  await dialog.getByRole('button', { name: 'Create register snapshot', exact: true }).click()
  await expect(dialog.getByText('Snapshot created. Download it when you are ready.', { exact: true })).toBeVisible()
  const downloadPending = page.waitForEvent('download')
  await dialog.getByRole('button', { name: 'Download handover', exact: true }).click()
  const download = await downloadPending
  expect(download.suggestedFilename()).toBe('documentation-handover.zip')
  expect(await download.failure()).toBeNull()
})

test('project auditor reconciliation remains available beside the simplified register', async ({ page }) => {
  await loginAsAdmin(page)
  const { register } = await seedRegister(page)
  const projectId = await seedAuditProject(page, register.jurisdiction_id)
  await page.goto(`/certification-projects?project=${projectId}&section=auditor-requests&register=${register.id}`)
  await expect(page.getByRole('heading', { name: 'Audit request reconciliation', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Map auditor request', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Map auditor request', exact: true })
  await dialog.getByRole('combobox', { name: 'Project audit form', exact: true }).selectOption({ label: 'Synthetic auditor request form' })
  await dialog.getByRole('combobox', { name: 'Audit form request', exact: true }).selectOption('auditor_report')
  await dialog.getByRole('textbox', { name: 'Auditor request ID', exact: true }).fill('AUDITOR-OUTPUT-1')
  await dialog.getByRole('textbox', { name: 'Audit list revision', exact: true }).fill('v2')
  await dialog.getByRole('combobox', { name: 'Responsible direction', exact: true }).selectOption('auditor_output')
  await dialog.getByRole('button', { name: 'Save request mapping', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Requests without matches (1)', exact: true })).toBeVisible()
  await expect(page.getByText('Auditor produces report', { exact: false }).first()).toBeVisible()
})
