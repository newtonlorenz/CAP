import { createHash } from 'node:crypto'
import { expect, test, type Locator, type Page } from '@playwright/test'
import { loginAsAdmin } from './testCredentials'

async function write(page: Page, method: 'post' | 'put', path: string, data: unknown) {
  const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrf_token')
  if (!csrf) throw new Error('The authenticated browser has no CSRF cookie.')
  const response = await page.request[method](path, { data, headers: { 'X-CSRF-Token': csrf.value } })
  expect(response.ok(), `${method} ${path}: ${response.status()}`).toBeTruthy()
  return response.json()
}

async function fixture(page: Page, kind: 'review' | 'application', { isolatedSource = false } = {}) {
  const suffix = `${kind}-${Date.now()}`
  const documents = (await (await page.request.get('/api/v1/documents?limit=500')).json()).items
  let document = documents.find((item: { name: string }) => item.name === 'E2E Document')
  expect(document).toBeTruthy()
  if (isolatedSource) {
    document = await write(page, 'post', '/api/v1/requirements/sets', {
      name: `SYNTHETIC isolated source ${suffix}`, jurisdiction_id: document.jurisdiction_id,
      document_type: 'standard', testing_frequency: 'one_off',
    })
    await write(page, 'post', '/api/v1/requirements', {
      document_id: document.id, reference_id: 'REQ-001', title: 'Synthetic source identity',
      text: 'Synthetic evidence source for the isolated version-change scenario.', requirement_type: 'mandatory',
    })
    await write(page, 'post', `/api/v1/documents/${document.id}/submit`, {})
    document = await write(page, 'post', `/api/v1/documents/${document.id}/approve`, {})
  }
  const requirements = (await (await page.request.get(`/api/v1/requirements?document_id=${document.id}&limit=500`)).json()).items
  const requirement = requirements.find((item: { reference_id: string }) => item.reference_id === 'REQ-001')
  expect(requirement).toBeTruthy()
  const versions = (await (await page.request.get(`/api/v1/requirements/sets/${document.id}/versions`)).json()).items
  const sourceVersion = versions.find((item: { id: string }) => item.id === requirement.requirement_set_version_id)
  expect(sourceVersion).toBeTruthy()
  const processName = `SYNTHETIC canonical process ${suffix}`
  let process: { id: string }, caseId: string | undefined
  if (kind === 'review') {
    process = await write(page, 'post', '/api/v1/review-cycles', {
      name: processName, jurisdiction_id: document.jurisdiction_id, scope: 'documents', document_ids: [document.id],
    })
  } else {
    process = await write(page, 'post', '/api/v1/applications', {
      name: processName, scope: 'annex_only', jurisdiction_id: document.jurisdiction_id, visibility: 'organisation',
    })
    const withForm = await write(page, 'post', `/api/v1/applications/${process.id}/components`, {
      expected_revision: (process as { revision?: number }).revision, name: 'Synthetic source form', kind: 'annex',
      form_fields: [{ key: 'proof', label: 'Synthetic source evidence question', type: 'evidence', required: false,
        source: { kind: 'requirement', document_id: document.id, document_name: document.name,
          document_status: document.status, jurisdiction_id: document.jurisdiction_id,
          requirement_id: requirement.id, requirement_set_version_id: requirement.requirement_set_version_id,
          version_number: sourceVersion.version_number, version_status: 'approved', reference_id: requirement.reference_id,
          text_sha256: createHash('sha256').update(requirement.text).digest('hex') } }],
    })
    caseId = withForm.components[0].case_id
  }
  const register = await write(page, 'post', '/api/v1/documentation/registers', {
    name: `SYNTHETIC process register ${suffix}`, jurisdiction_id: document.jurisdiction_id,
  })
  const row = await write(page, 'post', `/api/v1/documentation/registers/${register.id}/expectations`, {
    required_documentation: `SYNTHETIC process row ${suffix}`, source_reference: 'REQ-001',
    description: '', document_name: 'Original spreadsheet document name',
  })
  const evidence = []
  for (const prefix of ['Register selected note', 'Process owner selected note']) {
    if (kind === 'review' && evidence.length === 0) {
      const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrf_token')!
      const uploaded = await page.request.post('/api/v1/preparation/evidence/upload', {
        multipart: { title: `${prefix} ${suffix}`, visibility: 'organisation',
          file: { name: 'canonical-synthetic.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic canonical attachment bytes') } },
        headers: { 'X-CSRF-Token': csrf.value },
      })
      expect(uploaded.status()).toBe(201)
      evidence.push(await uploaded.json())
    } else evidence.push(await write(page, 'post', '/api/v1/preparation/evidence', {
      title: `${prefix} ${suffix}`, kind: 'note', body: `Synthetic canonical evidence for ${suffix}`, visibility: 'organisation',
    }))
  }
  return { kind, process, processName, register, row, evidence, caseId, document, requirement }
}

for (const kind of ['review', 'application'] as const) {
  test(`explicit ${kind} process mapping edits its canonical evidence collection in both directions`, async ({ page }) => {
    test.setTimeout(100_000)
    const pageErrors: string[] = []
    page.on('pageerror', error => pageErrors.push(error.message))
    await loginAsAdmin(page)
    const data = await fixture(page, kind)
    const evidenceBefore = (await (await page.request.get('/api/v1/preparation/evidence?limit=500')).json()).items
    const returnPath = `/library?section=documentation&register=${data.register.id}`
    await page.goto(returnPath)
    const table = page.getByRole('table', { name: 'Documentation register entries', exact: true })
    const row = table.getByRole('row').filter({ hasText: data.row.required_documentation })
    await expect(row).toBeVisible({ timeout: 20_000 })
    await page.getByRole('button', { name: 'Link process', exact: true }).click()
    let dialog = page.getByRole('dialog', { name: 'Link process', exact: true })
    if (kind === 'application') await dialog.getByRole('button', { name: 'Licence application', exact: true }).click()
    await dialog.getByRole('searchbox', { name: 'Search processes', exact: true }).fill(data.processName)
    await dialog.getByRole('radio', { name: new RegExp(data.processName) }).check()
    await dialog.getByRole('button', { name: 'Save process link', exact: true }).click()
    await expect(dialog).toHaveCount(0, { timeout: 20_000 })
    // A printed reference remains unmatched until the user chooses its exact process target.
    await row.getByRole('button', { name: 'Match reference', exact: true }).click()
    dialog = page.getByRole('dialog', { name: 'Match process reference', exact: true })
    await dialog.getByRole('searchbox', { name: 'Search process requirements', exact: true }).fill('REQ-001')
    await dialog.getByRole('checkbox', { name: /REQ-001/ }).check()
    await dialog.getByRole('button', { name: 'Save reference matches', exact: true }).click()
    await expect(dialog).toHaveCount(0, { timeout: 20_000 })
    await row.getByRole('button', { name: 'Manage documents', exact: true }).click()
    const documents = page.getByRole('dialog', { name: 'Process documents', exact: true })
    if (kind === 'review') {
      await documents.getByRole('button', { name: 'Link library evidence', exact: true }).click()
      dialog = page.getByRole('dialog', { name: 'Reuse evidence from the library', exact: true })
      await dialog.getByRole('searchbox', { name: 'Search available evidence', exact: true }).fill(data.evidence[0].title)
      await dialog.getByRole('checkbox', { name: new RegExp(data.evidence[0].title) }).check()
      await dialog.getByRole('textbox', { name: 'Assessment explanation', exact: true }).fill('Synthetic document selection from the register')
      await dialog.getByRole('button', { name: 'Save evidence links', exact: true }).click()
      await expect(dialog).toHaveCount(0, { timeout: 20_000 })
    } else {
      const attached = documents.getByRole('region', { name: 'Attached evidence', exact: true })
      await attached.getByRole('button', { name: 'Add evidence', exact: true }).click()
      await attached.getByRole('searchbox', { name: 'Search shared evidence', exact: true }).fill(data.evidence[0].title)
      await attached.getByRole('button', { name: `Attach ${data.evidence[0].title}`, exact: true }).click()
      await documents.getByRole('button', { name: 'Save documents', exact: true }).click()
      await expect(documents.getByText('Documents saved to the existing form question. Review acceptance is separate.', { exact: true })).toBeVisible()
    }
    await expect(documents.getByText(data.evidence[0].title, { exact: true })).toBeVisible()
    await documents.getByRole('link', { name: 'Open evidence collection', exact: true }).click()
    await expect(page).toHaveURL(kind === 'review' ? /\/review-cycles\// : /\/licence-applications\?/)
    expect(new URL(page.url()).searchParams.get('return_register')).toContain(data.register.id)
    await expect(page.getByText(data.evidence[0].title, { exact: true }).first()).toBeVisible({ timeout: 20_000 })
    // The owner editor changes the same collection; the register must refetch it.
    const currentRow = await (await page.request.get(`/api/v1/documentation/expectations/${data.row.id}`)).json()
    const target = currentRow.process_targets[0]
    if (kind === 'review') {
      expect(target.collection.items.map((item: { evidence_id: string }) => item.evidence_id)).toEqual([data.evidence[0].id])
      const initiallySaved = await (await page.request.get(`/api/v1${target.collection.shared_evidence_uri}`)).json()
      expect(initiallySaved.items.map((item: { evidence_id: string }) => item.evidence_id)).toEqual([data.evidence[0].id])
      await expect((await page.request.get(`/api/v1/preparation/evidence/${data.evidence[0].id}/download`)).body()).resolves.toEqual(Buffer.from('Synthetic canonical attachment bytes'))
      await page.getByRole('button', { name: 'Link library evidence', exact: true }).click()
      dialog = page.getByRole('dialog', { name: 'Reuse evidence from the library', exact: true })
      await dialog.getByRole('searchbox', { name: 'Search available evidence', exact: true }).fill(data.evidence[0].title)
      await dialog.getByRole('checkbox', { name: new RegExp(data.evidence[0].title) }).uncheck()
      await dialog.getByRole('searchbox', { name: 'Search available evidence', exact: true }).fill(data.evidence[1].title)
      await dialog.getByRole('checkbox', { name: new RegExp(data.evidence[1].title) }).check()
      await dialog.getByRole('textbox', { name: 'Assessment explanation', exact: true }).fill('Synthetic review UI replacement')
      await dialog.getByRole('button', { name: 'Save evidence links', exact: true }).click()
      await expect(dialog).toHaveCount(0, { timeout: 20_000 })
      await expect(page.getByText(data.evidence[1].title, { exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Link library evidence', exact: true }).click()
      dialog = page.getByRole('dialog', { name: 'Reuse evidence from the library', exact: true })
      await expect(dialog.getByRole('button', { name: 'Save evidence links', exact: true })).toBeDisabled()
      await dialog.getByRole('textbox', { name: 'Evidence locator', exact: true }).fill('Section 3')
      await dialog.getByRole('button', { name: 'Save evidence links', exact: true }).click()
      await expect(dialog).toHaveCount(0, { timeout: 20_000 })
      const repeated = await (await page.request.get(`/api/v1${target.collection.shared_evidence_uri}`)).json()
      expect(repeated.items.map((item: { evidence_id: string }) => item.evidence_id)).toEqual([data.evidence[1].id])
    } else {
      await write(page, 'put', `/api/v1${target.collection.response_uri}`, {
        expected_revision: target.collection.case_revision, evidence_ids: [data.evidence[1].id],
        value: target.collection.response.value, not_applicable_reason: target.collection.response.not_applicable_reason,
      })
    }
    if (kind === 'review') await page.getByRole('link', { name: 'Back to documentation register', exact: true }).click()
    else await page.goto(returnPath)
    await expect(row.getByRole('cell').nth(3).getByText(data.evidence[1].title, { exact: true })).toBeVisible({ timeout: 20_000 })
    await expect(row.getByRole('cell').nth(3).getByText(data.evidence[0].title, { exact: true })).toHaveCount(0)
    await expect(row.getByRole('cell').last().getByRole('button', { name: 'Manage documents', exact: true })).toBeVisible()
    await page.reload()
    await expect(row.getByRole('cell').nth(3)).toContainText(data.evidence[1].title, { timeout: 20_000 })
    for (let index = 0; index < 4; index++) await expect(row.getByRole('cell').nth(index).getByRole('button')).toHaveCount(0)
    const evidenceAfter = (await (await page.request.get('/api/v1/preparation/evidence?limit=500')).json()).items
    expect(evidenceAfter.map((item: { id: string }) => item.id).sort()).toEqual(evidenceBefore.map((item: { id: string }) => item.id).sort())
    const finalRow = await (await page.request.get(`/api/v1/documentation/expectations/${data.row.id}`)).json()
    expect(finalRow.process_targets[0].collection.items.map((item: { evidence_id: string }) => item.evidence_id)).toEqual([data.evidence[1].id])
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: `/tmp/cap-documentation-process-${kind}.png`, fullPage: true })
    expect(pageErrors).toEqual([])
  })
}

test('optional row owners persist while two rows keep different certification review collections', async ({ page }) => {
  test.setTimeout(160_000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await loginAsAdmin(page)
  const data = await fixture(page, 'review')
  const otherName = `SYNTHETIC second row review ${Date.now()}`
  const otherReview = await write(page, 'post', '/api/v1/review-cycles', {
    name: otherName, jurisdiction_id: data.document.jurisdiction_id, scope: 'documents', document_ids: [data.document.id],
  })
  const second = await write(page, 'post', `/api/v1/documentation/registers/${data.register.id}/expectations`, {
    required_documentation: `SYNTHETIC independent row ${Date.now()}`, source_reference: 'REQ-001',
    description: '', document_name: '',
  })
  const users = (await (await page.request.get('/api/v1/users/mentions?limit=1000')).json()).items
  expect(users.length).toBeGreaterThanOrEqual(2)
  const firstOwner = users[0]
  const secondOwner = users.find((user: { id: string }) => user.id !== firstOwner.id)
  expect(secondOwner).toBeTruthy()
  const returnPath = `/library?section=documentation&register=${data.register.id}`
  await page.goto(returnPath)
  const table = page.getByRole('table', { name: 'Documentation register entries', exact: true })
  await expect(table.getByRole('columnheader')).toHaveText([
    'Document / record required', 'SCP reference', 'Comment/explanation', 'Document', 'Actions',
  ], { timeout: 20_000 })
  const firstRow = table.getByRole('row').filter({ hasText: data.row.required_documentation })
  const secondRow = table.getByRole('row').filter({ hasText: second.required_documentation })
  const assign = async (row: Locator, ownerId: string | null) => {
    await row.getByRole('button', { name: /^Assign user for / }).click()
    const dialog = page.getByRole('dialog', { name: 'Assign responsible owner', exact: true })
    if (ownerId) await dialog.getByRole('combobox', { name: 'Owner', exact: true }).selectOption(ownerId)
    else await dialog.getByRole('button', { name: 'Clear assignment', exact: true }).click()
    await dialog.getByRole('button', { name: 'Save assignment', exact: true }).click()
    await expect(dialog).toHaveCount(0, { timeout: 20_000 })
  }
  await assign(firstRow, firstOwner.id)
  await assign(secondRow, secondOwner.id)
  await page.reload()
  await expect(firstRow.getByRole('cell').first()).toContainText(`Responsible owner: ${firstOwner.full_name}`, { timeout: 20_000 })
  await expect(secondRow.getByRole('cell').first()).toContainText(`Responsible owner: ${secondOwner.full_name}`)
  await assign(firstRow, null)
  await page.reload()
  await expect(firstRow.getByRole('cell').first()).toContainText('Responsible owner: Unassigned', { timeout: 20_000 })
  await expect(secondRow.getByRole('cell').first()).toContainText(`Responsible owner: ${secondOwner.full_name}`)

  const matchReview = async (row: Locator, name: string, cycleId: string) => {
    await row.getByRole('button', { name: /^Link certification review for / }).click()
    let dialog = page.getByRole('dialog', { name: 'Select certification review', exact: true })
    await dialog.getByRole('searchbox', { name: 'Search certification reviews', exact: true }).fill(name)
    await dialog.getByRole('radio', { name: new RegExp(name) }).check()
    await dialog.getByRole('button', { name: 'Save review link', exact: true }).click()
    await expect(dialog).toHaveCount(0, { timeout: 20_000 })
    dialog = page.getByRole('dialog', { name: 'Match process reference', exact: true })
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
    const reviewLink = row.getByRole('link', { name, exact: true })
    await expect(reviewLink).toHaveAttribute('href', new RegExp(`/review-cycles/${cycleId}\\?`))
    await reviewLink.click()
    await expect(page).toHaveURL(new RegExp(`/review-cycles/${cycleId}\\?`))
    expect(new URL(page.url()).searchParams.get('return_register')).toContain(data.register.id)
    await page.goBack()
    await row.getByRole('button', { name: 'Match reference', exact: true }).click()
    dialog = page.getByRole('dialog', { name: 'Match process reference', exact: true })
    await dialog.getByRole('searchbox', { name: 'Search process requirements', exact: true }).fill('REQ-001')
    await dialog.getByRole('checkbox', { name: /REQ-001/ }).check()
    await dialog.getByRole('button', { name: 'Save reference matches', exact: true }).click()
    await expect(dialog).toHaveCount(0, { timeout: 20_000 })
  }
  await matchReview(firstRow, data.processName, data.process.id)
  await matchReview(secondRow, otherName, otherReview.id)
  const attach = async (row: Locator, title: string) => {
    await row.getByRole('button', { name: 'Manage documents', exact: true }).click()
    const documents = page.getByRole('dialog', { name: 'Process documents', exact: true })
    await documents.getByRole('button', { name: 'Link library evidence', exact: true }).click()
    const picker = page.getByRole('dialog', { name: 'Reuse evidence from the library', exact: true })
    await picker.getByRole('searchbox', { name: 'Search available evidence', exact: true }).fill(title)
    await picker.getByRole('checkbox', { name: new RegExp(title) }).check()
    await picker.getByRole('textbox', { name: 'Assessment explanation', exact: true }).fill('Synthetic independent row evidence')
    await picker.getByRole('button', { name: 'Save evidence links', exact: true }).click()
    await expect(picker).toHaveCount(0)
    await expect(documents.getByText(title, { exact: true })).toBeVisible()
    await documents.getByRole('button', { name: 'Close dialog', exact: true }).click()
  }
  await attach(firstRow, data.evidence[0].title)
  await attach(secondRow, data.evidence[1].title)
  await page.reload()
  await expect(firstRow.getByRole('cell').nth(3)).toContainText(data.evidence[0].title, { timeout: 20_000 })
  await expect(firstRow.getByRole('cell').nth(3)).not.toContainText(data.evidence[1].title)
  await expect(secondRow.getByRole('cell').nth(3)).toContainText(data.evidence[1].title)
  await expect(secondRow.getByRole('cell').nth(3)).not.toContainText(data.evidence[0].title)
  const currentFirst = await (await page.request.get(`/api/v1/documentation/expectations/${data.row.id}`)).json()
  const currentSecond = await (await page.request.get(`/api/v1/documentation/expectations/${second.id}`)).json()
  expect(currentFirst.review_cycle_id).toBe(data.process.id)
  expect(currentSecond.review_cycle_id).toBe(otherReview.id)
  expect(currentFirst.source_reference).toBe('REQ-001')
  expect(currentSecond.source_reference).toBe('REQ-001')
  expect(currentFirst.owner_id).toBeNull()
  expect(currentSecond.owner_id).toBe(secondOwner.id)
  const replacement = await write(page, 'post', '/api/v1/preparation/evidence', {
    title: `SYNTHETIC row one replacement ${Date.now()}`, kind: 'note', body: 'Synthetic owner-side replacement', visibility: 'organisation',
  })
  const collection = currentFirst.process_targets[0].collection
  await write(page, 'put', `/api/v1${collection.shared_evidence_uri}`, {
    expected_evidence_changed_at: collection.evidence_changed_at,
    links: [{ evidence_id: replacement.id, rationale: 'Synthetic first-review-only change' }],
  })
  await page.reload()
  await expect(firstRow.getByRole('cell').nth(3)).toContainText(replacement.title, { timeout: 20_000 })
  await expect(firstRow.getByRole('cell').nth(3)).not.toContainText(data.evidence[0].title)
  await expect(secondRow.getByRole('cell').nth(3)).toContainText(data.evidence[1].title)
  await expect(secondRow.getByRole('cell').nth(3)).not.toContainText(replacement.title)
  await expect(table.getByRole('columnheader')).toHaveText([
    'Document / record required', 'SCP reference', 'Comment/explanation', 'Document', 'Actions',
  ])
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '/tmp/cap-documentation-row-owner-reviews.png', fullPage: true })
  expect(errors).toEqual([])
})

test('a saved register deep link cannot open the same licence field after its approved source changes', async ({ page }) => {
  test.setTimeout(100_000)
  await loginAsAdmin(page)
  const data = await fixture(page, 'application', { isolatedSource: true })
  const returnPath = `/library?section=documentation&register=${data.register.id}`
  await write(page, 'put', `/api/v1/documentation/registers/${data.register.id}/process`, {
    revision: (await (await page.request.get(`/api/v1/documentation/registers/${data.register.id}`)).json()).revision,
    review_cycle_id: null, application_id: data.process.id,
  })
  await write(page, 'put', `/api/v1/documentation/expectations/${data.row.id}/process-targets`, {
    revision: data.row.revision, targets: [{ case_id: data.caseId, field_key: 'proof',
      requirement_id: data.requirement.id, requirement_set_version_id: data.requirement.requirement_set_version_id }],
  })
  const stalePath = `/licence-applications?application=${data.process.id}&case=${data.caseId}&field=proof&return_register=${encodeURIComponent(returnPath)}&register_requirement=${data.requirement.id}&register_version=${data.requirement.requirement_set_version_id}`
  await page.goto(stalePath)
  await expect(page.getByText('Synthetic source evidence question', { exact: true }).first()).toBeVisible({ timeout: 20_000 })
  const cloned = await write(page, 'post', `/api/v1/requirements/sets/${data.document.id}/versions/clone`, {
    source_version_id: data.requirement.requirement_set_version_id, change_summary: 'Synthetic source identity race',
  })
  await write(page, 'post', `/api/v1/requirements/sets/${data.document.id}/versions/${cloned.id}/submit`, {})
  const approved = await write(page, 'post', `/api/v1/requirements/sets/${data.document.id}/versions/${cloned.id}/approve`, {})
  const replacements = (await (await page.request.get(`/api/v1/requirements?document_id=${data.document.id}&requirement_set_version_id=${approved.id}&limit=500`)).json()).items
  const replacement = replacements.find((item: { reference_id: string }) => item.reference_id === data.requirement.reference_id)
  expect(replacement.id).not.toBe(data.requirement.id)
  const current = await (await page.request.get(`/api/v1/preparation/cases/${data.caseId}`)).json()
  const fields = current.fields
  fields[0].source = { ...fields[0].source, requirement_id: replacement.id,
    requirement_set_version_id: approved.id, version_number: approved.version_number,
    text_sha256: createHash('sha256').update(replacement.text).digest('hex') }
  const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrf_token')!
  const changed = await page.request.patch(`/api/v1/preparation/cases/${data.caseId}`, {
    data: { expected_revision: current.revision, fields }, headers: { 'X-CSRF-Token': csrf.value },
  })
  expect(changed.ok()).toBeTruthy()
  const attempts: string[] = []
  page.on('request', request => {
    if (request.method() === 'PUT' && request.url().includes(`/preparation/cases/${data.caseId}/responses/`)) attempts.push(new URL(request.url()).pathname)
  })
  await page.goto(stalePath)
  await expect(page.getByRole('alert').filter({ hasText: 'The exact requirement version linked from the register is unavailable in this form question.' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('button', { name: 'Add evidence', exact: true })).toHaveCount(0)
  expect(attempts).toEqual([])
  await page.screenshot({ path: '/tmp/cap-documentation-process-stale-source.png', fullPage: true })
})

