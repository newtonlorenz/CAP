import { expect, test, type APIResponse, type Browser, type BrowserContext, type Page } from '@playwright/test'
import { e2eAdminPassword, loginAsAdmin } from './testCredentials'

type Pack = { id: string; name: string; revision: number; status: string; readiness: { ready: boolean; blockers: { code: string; message: string }[] }; components: { id: string; name: string; kind: string; case_id: string | null }[] }
type Case = { id: string; fields: { label: string }[]; responses: { field_key: string; value: unknown }[]; original_evidence_ids: string[] }
type Policy = { revision: number; visibility: 'secret' | 'restricted' | 'organisation' }
type Person = { id: string; email: string; full_name: string }

async function json<T>(response: APIResponse): Promise<T> {
  expect(response.ok(), await response.text()).toBeTruthy()
  return response.json() as Promise<T>
}
async function csrf(page: Page) {
  const token = (await page.context().cookies()).find(cookie => cookie.name === 'csrf_token')
  expect(token).toBeDefined()
  await page.context().setExtraHTTPHeaders({ 'X-CSRF-Token': token!.value })
}
async function admin(page: Page) { await loginAsAdmin(page); await csrf(page) }
async function rolePage(browser: Browser, email: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: 'http://127.0.0.1:15173' })
  const page = await context.newPage()
  await page.goto('/login')
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(e2eAdminPassword!)
  await page.locator('button[type="submit"]').click()
  await page.waitForURL('/')
  await page.getByLabel('Jurisdiction selector').selectOption({ label: 'Example jurisdiction' })
  await csrf(page)
  return { context, page }
}
async function selectMarket(page: Page, code: string) {
  const markets = await json<{ items: { id: string; code: string; name: string }[] }>(await page.request.get('/api/v1/jurisdictions?limit=1000'))
  const market = markets.items.find(item => item.code.toUpperCase() === code)
  expect(market, `${code} market fixture`).toBeDefined()
  await page.getByLabel('Jurisdiction selector').selectOption(market!.id)
}
async function createPack(page: Page, name: string, people = ''): Promise<Pack> {
  await page.goto('/licence-applications')
  await page.getByRole('button', { name: 'New licence pack', exact: true }).click()
  await page.getByLabel('Pack name', { exact: true }).fill(name)
  await page.getByLabel('Applicant', { exact: true }).fill('Synthetic Operator Ltd')
  await page.getByLabel('Activities and scope').fill('Synthetic licence preparation')
  // The first action changes when the asynchronous market profile finishes loading.
  await expect(page.getByRole('button', { name: /^(Continue to market questions|Review proposed contents|Continue to owners and access)$/ })).toBeEnabled()
  const marketQuestions = page.getByRole('button', { name: 'Continue to market questions' })
  const reviewContents = page.getByRole('button', { name: 'Review proposed contents' })
  let reviewsChecklist = false
  if (await marketQuestions.isVisible()) {
    await marketQuestions.click()
    if (people) await page.getByRole('textbox', { name: /People|persons|individual/i }).fill(people)
    await reviewContents.click()
    reviewsChecklist = true
  } else if (await reviewContents.isVisible()) {
    await reviewContents.click()
    reviewsChecklist = true
  }
  if (reviewsChecklist) await page.getByRole('checkbox', { name: /I have reviewed this proposed checklist/ }).check()
  await page.getByRole('button', { name: 'Continue to owners and access' }).click()
  const response = page.waitForResponse(item => item.url().endsWith('/applications/guided') && item.request().method() === 'POST')
  await page.getByRole('button', { name: 'Create licence pack', exact: true }).click()
  const pack = await json<Pack>(await response)
  await expect(page).toHaveURL(new RegExp(`application=${pack.id}`))
  await expect(page.getByRole('heading', { name: pack.name, exact: true })).toBeVisible()
  return pack
}
async function tab(page: Page, name: string) { await page.getByRole('button', { name, exact: true }).click() }
async function freshPackForms(page: Page) {
  await tab(page, 'Forms and documents')
  await expect(page.getByRole('dialog', { name: 'Changes are not saved yet' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Forms and documents', exact: true })).toBeVisible()
}
async function openAddForm(page: Page) {
  const summary = page.locator('summary').filter({ hasText: /^Add form or document$/ })
  const details = summary.locator('..')
  if (!(await details.evaluate((node: HTMLDetailsElement) => node.open))) await summary.click()
  await expect(details.getByLabel('Form or document name')).toBeVisible()
}
async function packFrom(page: Page, id: string) { return json<Pack>(await page.request.get(`/api/v1/applications/${id}`)) }
async function caseFrom(page: Page, id: string) { return json<Case>(await page.request.get(`/api/v1/preparation/cases/${id}`)) }
async function grant(page: Page, kind: string, id: string, grants: { subject_type: 'user'; subject_id: string; permissions: string[] }[]) {
  const policy = await json<Policy>(await page.request.get(`/api/v1/access/${kind}/${id}`))
  await json(await page.request.put(`/api/v1/access/${kind}/${id}`, { data: { expected_revision: policy.revision, visibility: policy.visibility, grants, reason: 'Synthetic pack permission exercise' } }))
}

test.use({ actionTimeout: 15000 })

test('reviewed import, private upload retry, unsaved navigation and repeat blank keep source work separate', async ({ page }) => {
  test.setTimeout(150000)
  await admin(page)
  await selectMarket(page, 'DK')
  const pack = await createPack(page, `Pack form privacy ${Date.now()}`, 'Director One\nDirector Two')
  const source = pack.components.find(item => item.kind === 'annex' && item.name.includes('Director One'))!
  expect(source).toBeDefined()
  await freshPackForms(page)
  const row = page.locator('article').filter({ has: page.getByRole('heading', { name: source.name, exact: true }) })
  await row.getByRole('button', { name: `Set up ${source.name}` }).click()
  await row.locator('summary').filter({ hasText: 'Import questions from Excel' }).click()
  await row.locator('summary').filter({ hasText: 'Or paste cells from Excel' }).click()
  await row.getByLabel('Copied cells, including column headings').fill('Section\tQuestion\tType\nDirector\tDirector declaration\ttext')
  await row.getByRole('button', { name: 'Preview pasted questions' }).click()
  await expect(row.getByRole('list', { name: 'Imported question preview' })).toContainText('Director declaration')
  await row.getByRole('button', { name: /Add 1 questions to form/ }).click()
  await expect(row.getByText('Review 1 imported questions')).toBeVisible()
  await row.getByRole('button', { name: 'Confirm and add questions' }).click()
  await expect(row.getByLabel('Question 1', { exact: true })).toHaveValue('Director declaration')

  await row.locator('summary').filter({ hasText: /^Original form or source files/ }).click()
  const original = row.getByLabel('Upload a private source file')
  await original.setInputFiles('e2e/fixtures/test.pdf')
  await row.getByLabel('Title (optional)').fill('Private director source')
  await page.route('**/api/v1/preparation/evidence/upload', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic upload outage' }) }))
  await row.getByRole('button', { name: 'Upload and attach' }).click()
  await expect(row.getByRole('alert')).toContainText('Synthetic upload outage')
  expect(await original.evaluate((node: HTMLInputElement) => node.files?.[0]?.name)).toBe('test.pdf')
  await expect(row.getByLabel('Title (optional)')).toHaveValue('Private director source')
  await page.unroute('**/api/v1/preparation/evidence/upload')
  const upload = page.waitForResponse(item => item.url().endsWith('/preparation/evidence/upload') && item.request().method() === 'POST')
  await row.getByRole('button', { name: 'Upload and attach' }).click()
  const evidence = await json<{ id: string; access: { visibility: string } }>(await upload)
  expect(evidence.access.visibility).toBe('secret')
  await row.getByRole('button', { name: 'Save form or document' }).click()
  await expect(row.getByRole('button', { name: `Open ${source.name}` })).toBeVisible()
  const configured = await packFrom(page, pack.id)
  const sourceCaseId = configured.components.find(item => item.id === source.id)!.case_id!
  const sourceCase = await caseFrom(page, sourceCaseId)
  expect(sourceCase.fields.map(field => field.label)).toContain('Director declaration')
  expect(sourceCase.original_evidence_ids).toEqual([evidence.id])

  await row.getByRole('button', { name: `Open ${source.name}` }).click()
  await page.getByRole('textbox', { name: 'Director declaration', exact: true }).fill('Private synthetic answer')
  await page.getByRole('button', { name: 'Accept response', exact: true }).click()
  await expect(page.getByText('Accepted', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Return to pack' }).click()
  page.once('dialog', dialog => dialog.accept('Another blank declaration'))
  const duplicateResponse = page.waitForResponse(item => item.url().endsWith(`/components/${source.id}/duplicate`) && item.request().method() === 'POST')
  await row.getByRole('button', { name: 'Add another blank' }).click()
  const duplicatedPack = await json<Pack>(await duplicateResponse)
  const duplicate = duplicatedPack.components.find(item => item.name === 'Another blank declaration')!
  expect(duplicate).toBeDefined()
  expect(duplicate.case_id).not.toBe(sourceCaseId)
  const blank = await caseFrom(page, duplicate.case_id!)
  expect(blank.fields.map(field => field.label)).toEqual(sourceCase.fields.map(field => field.label))
  expect(blank.responses).toEqual([])
  expect(blank.original_evidence_ids).toEqual([])
  expect((await caseFrom(page, sourceCaseId)).responses.length).toBeGreaterThan(0)

  const second = duplicatedPack.components.find(item => item.kind === 'annex' && item.name.includes('Director Two'))!
  const secondRow = page.locator('article').filter({ has: page.getByRole('heading', { name: second.name, exact: true }) })
  await secondRow.getByRole('button', { name: `Set up ${second.name}` }).click()
  await secondRow.getByRole('button', { name: 'Add question' }).click()
  await secondRow.getByLabel('Question 1', { exact: true }).fill('Unsaved question')
  await tab(page, 'Overview')
  const blocked = page.getByRole('dialog', { name: 'Changes are not saved yet' })
  await expect(blocked).toBeVisible()
  await blocked.getByRole('button', { name: 'Cancel' }).click()
  await expect(secondRow.getByLabel('Question 1', { exact: true })).toHaveValue('Unsaved question')
  expect((await packFrom(page, pack.id)).components.find(item => item.id === second.id)?.case_id).toBeNull()
})

test('manager, contributor, approver and summary reader see only their granted pack and original file controls', async ({ page, browser }) => {
  test.setTimeout(180000)
  await admin(page)
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const createPerson = async (role: string): Promise<Person> => json(await page.request.post('/api/v1/users', { data: { email: `pack-${role}-${suffix}@example.com`, password: e2eAdminPassword, full_name: `Pack ${role} ${suffix}`, role } }))
  const manager = await createPerson('manager')
  const contributor = await createPerson('contributor')
  const approver = await createPerson('approver')
  const summary = await createPerson('assigned_reviewer')
  const managerSession = await rolePage(browser, manager.email)
  const contributorSession = await rolePage(browser, contributor.email)
  const approverSession = await rolePage(browser, approver.email)
  const summarySession = await rolePage(browser, summary.email)
  try {
    const work = managerSession.page
    await selectMarket(work, 'SE')
    const pack = await createPack(work, `Private Swedish pack ${suffix}`)
    expect(pack.components).toHaveLength(0)
    await freshPackForms(work)
    await openAddForm(work)
    await work.getByLabel('Form or document name').fill('Operator declaration')
    await work.getByRole('button', { name: 'Add question' }).click()
    await work.getByLabel('Question 1', { exact: true }).fill('Operator name')
    await work.locator('summary').filter({ hasText: /^Original form or source files/ }).click()
    const upload = work.waitForResponse(item => item.url().endsWith('/preparation/evidence/upload') && item.request().method() === 'POST')
    await work.getByLabel('Upload a private source file').setInputFiles('e2e/fixtures/test.pdf')
    await work.getByRole('button', { name: 'Upload and attach' }).click()
    const original = await json<{ id: string }>(await upload)
    const added = work.waitForResponse(item => item.url().endsWith(`/applications/${pack.id}/components`) && item.request().method() === 'POST')
    await work.getByRole('button', { name: 'Add form or document', exact: true }).click()
    const configured = await json<Pack>(await added)
    await expect(work.getByRole('button', { name: 'Open Operator declaration' })).toBeVisible()
    const formId = configured.components[0].case_id!
    expect((await caseFrom(work, formId)).original_evidence_ids).toEqual([original.id])
    await work.getByRole('button', { name: 'Open Operator declaration' }).click()
    await work.getByRole('textbox', { name: 'Operator name', exact: true }).fill('Synthetic Operator')
    await work.getByRole('button', { name: 'Accept response', exact: true }).click()
    await expect(work.getByText('Accepted', { exact: true })).toBeVisible()
    await work.getByRole('button', { name: 'Return to pack' }).click()
    const readyPack = await packFrom(work, pack.id)
    expect(readyPack.readiness.ready, JSON.stringify(readyPack.readiness.blockers)).toBeTruthy()
    await tab(work, 'Approval and submission')
    await expect(work.getByRole('button', { name: 'Send for internal review' })).toBeEnabled()
    await work.getByRole('button', { name: 'Send for internal review' }).click()
    await work.getByRole('button', { name: 'Confirm: Send for internal review' }).click()

    const packGrants = [
      { subject_type: 'user' as const, subject_id: contributor.id, permissions: ['summary', 'view', 'edit'] },
      { subject_type: 'user' as const, subject_id: approver.id, permissions: ['summary', 'view', 'approve'] },
      { subject_type: 'user' as const, subject_id: summary.id, permissions: ['summary'] },
    ]
    // The original file is separately granted first; its parent pack still denies access.
    await grant(work, 'preparation_evidence', original.id, [
      { subject_type: 'user', subject_id: contributor.id, permissions: ['view'] },
      { subject_type: 'user', subject_id: approver.id, permissions: ['view'] },
    ])
    const denied = await contributorSession.page.request.get(`/api/v1/preparation/evidence/${original.id}`)
    expect([403, 404]).toContain(denied.status())
    await grant(work, 'application', pack.id, packGrants)
    await grant(work, 'preparation_case', formId, [
      { subject_type: 'user', subject_id: contributor.id, permissions: ['view', 'edit'] },
      { subject_type: 'user', subject_id: approver.id, permissions: ['view'] },
    ])

    const contributorPage = contributorSession.page
    await contributorPage.goto(`/licence-applications?application=${pack.id}&tab=forms`)
    await expect(contributorPage.getByRole('heading', { name: pack.name })).toBeVisible()
    await expect(contributorPage.getByRole('button', { name: 'Open Operator declaration' })).toBeVisible()
    await expect(contributorPage.getByRole('button', { name: 'Edit Operator declaration' })).toHaveCount(0)
    await contributorPage.getByRole('button', { name: 'Open Operator declaration' }).click()
    await expect(contributorPage.getByText('Original form documents (1)')).toBeVisible()
    await contributorPage.getByText('Original form documents (1)').click()
    await expect(contributorPage.getByText('test.pdf', { exact: true }).first()).toBeVisible()
    await expect(contributorPage.getByRole('button', { name: 'Accept response' })).toHaveCount(0)

    const approverPage = approverSession.page
    await approverPage.goto(`/licence-applications?application=${pack.id}&tab=approval`)
    await expect(approverPage.getByRole('button', { name: 'Approve pack internally' })).toBeEnabled()
    await expect(approverPage.getByRole('button', { name: 'Add form or document' })).toHaveCount(0)
    await expect(approverPage.getByRole('button', { name: 'Who can access this?' })).toHaveCount(0)

    const summaryPage = summarySession.page
    await summaryPage.goto(`/licence-applications?application=${pack.id}`)
    await expect(summaryPage.getByText('You have summary access.')).toBeVisible()
    await expect(summaryPage.getByRole('button', { name: 'Open Operator declaration' })).toHaveCount(0)
    const summaryOriginal = await summaryPage.request.get(`/api/v1/preparation/evidence/${original.id}`)
    expect([403, 404]).toContain(summaryOriginal.status())
  } finally {
    await Promise.all([managerSession.context.close(), contributorSession.context.close(), approverSession.context.close(), summarySession.context.close()])
  }
})
