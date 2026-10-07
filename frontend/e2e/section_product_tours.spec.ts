import { expect, test, type Page } from '@playwright/test'
import type { CertificationProject, SubmissionPackage } from '../src/types'
import type { LicenceApplication } from '../src/types/applications'

const userId = 'synthetic-section-tour-user'
const invitation = (page: Page) => page.getByRole('region', { name: 'Product tour invitation' })
const popover = (page: Page) => page.locator('.cap-product-tour')
const empty = { items: [], total: 0, limit: 1000, offset: 0, skip: 0 }
const project: CertificationProject = {
  id: 'synthetic-project', organization_id: 'synthetic-organisation', source_document_id: null,
  jurisdiction_id: 'synthetic-market', name: 'Synthetic certification', description: 'Synthetic test scope',
  stage: 'intake', status: 'active', owner_id: userId, created_by: userId, started_at: null,
  target_submission_date: null, assurance_type: 'certification', provider_name: 'Synthetic provider',
  engagement_reference: null, assurance_scope: 'Synthetic assurance scope', system_version: null,
  scheduled_test_date: null, actual_test_date: null, report_reference: null, report_outcome: 'not_recorded',
  report_issued_at: null, report_link: null, completed_at: null, created_at: '2026-01-01T00:00:00Z',
  requirement_set_ids: [], baseline_versions: [],
}
const pack: LicenceApplication = {
  id: 'synthetic-pack', name: 'Synthetic licence pack', scope: 'full_pack', jurisdiction_id: 'synthetic-market',
  applicant: 'Synthetic applicant', authority: 'Synthetic authority', description: 'Synthetic licence scope',
  owner_id: userId, due_date: null, status: 'draft', revision: 1, outcome: null,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  components: [{ id: 'synthetic-component', name: 'Synthetic application form', kind: 'form', required: true,
    included: true, owner_id: userId, due_date: null, case_id: null, evidence_id: null, case_name: null,
    ready: false, blockers: [], form_field_count: 0 }], followups: [], snapshots: [], history: [],
  readiness: { ready: false, required_count: 1, ready_count: 0, blockers: [] },
}

const submissionPackage: SubmissionPackage = {
  id: 'synthetic-package', project_id: project.id, review_cycle_id: null, snapshot_id: null,
  version: 'synthetic-v1', status: 'draft', checklist_json: null, approval_requested_at: null,
  approved_by: null, approved_at: null, locked_at: null, created_by: userId, created_at: '2026-01-01T00:00:00Z',
}

async function mockWorkspace(page: Page, options: { packFailure?: boolean; summaryAccess?: boolean; includePackage?: boolean } = {}) {
  const mutations: string[] = []
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    if (request.method() !== 'GET' && !path.startsWith('/auth/')) mutations.push(`${request.method()} ${path}`)
    if (path.startsWith('/applications/') && options.packFailure) {
      await route.fulfill({ status: 503, json: { detail: 'Synthetic service unavailable' } }); return
    }
    if (options.includePackage && path === '/submission-packages') {
      await route.fulfill({ json: { ...empty, items: [submissionPackage], total: 1 } }); return
    }
    if (options.includePackage && path === '/submission-packages/synthetic-package/gate-check') {
      await route.fulfill({ json: {
        package_id: submissionPackage.id, project_id: project.id, status: 'draft',
        review_cycle_linked: false, review_cycle_closed: false, review_cycle_snapshot_id: null,
        snapshot_bound: false, required_artifacts_total: 0, required_artifacts_included: 0,
        missing_required_artifacts: [], checks_passed: false,
        blocking_reasons: ['Synthetic submission assessment still needs closure.'],
      } }); return
    }
    const json = path === '/auth/me' ? {
      id: userId, organization_id: 'synthetic-organisation', full_name: 'Synthetic Tour User',
      email: 'synthetic-section-tour@example.test', role: 'admin', active: true, created_at: '2026-01-01T00:00:00Z',
    } : path === '/jurisdictions' ? { ...empty, items: [{ id: 'synthetic-market', name: 'Synthetic market', code: 'TEST', active: true }], total: 1 }
      : path === '/users/mentions' ? { ...empty, items: [{ id: userId, full_name: 'Synthetic Tour User', email: 'synthetic-section-tour@example.test' }], total: 1 }
        : path === '/applications/synthetic-pack' ? { ...pack, summary_only: options.summaryAccess || false }
          : path === '/applications' ? { ...empty, items: [pack], total: 1 }
            : path === '/certification-projects' ? { ...empty, items: [project], total: 1 }
              : path === '/product-feedback/config' ? { enabled: false }
                : path === '/auth/notification-settings' ? { review_mentions: true, review_reminders: false }
                  : empty
    await route.fulfill({ json })
  })
  return mutations
}

async function storedState(page: Page, tourId: string) {
  return page.evaluate(({ id, section }) => {
    const key = `cap:product-tour:v2:${encodeURIComponent(id)}:${encodeURIComponent(section)}`
    return JSON.parse(localStorage.getItem(key) || 'null')
  }, { id: userId, section: tourId })
}

async function replay(page: Page) {
  if (await page.getByTestId('mobile-nav-toggle').isVisible()) await page.getByTestId('mobile-nav-toggle').click()
  const resources = page.getByRole('button', { name: 'Resources', exact: true }).filter({ visible: true })
  if (await resources.getAttribute('aria-expanded') === 'false') await resources.click()
  await page.getByRole('button', { name: 'Product tour', exact: true }).filter({ visible: true }).click()
}

// Follow the controls exposed to a user; assertions concern browser behaviour rather
// than reproducing catalogue strings or deriving an expected result from the catalogue.
async function walkTour(page: Page, options: { firstStep?: number; viewportWidth?: number } = {}) {
  let anchored = 0
  let total = 0
  const guidance: string[] = []
  let expectedStep = (options.firstStep || 0) + 1
  for (let index = 0; index < 30; index += 1) {
    await expect(popover(page)).toBeVisible()
    const progressLabel = popover(page).locator('.driver-popover-progress-text')
    await expect(progressLabel).toContainText(`Step ${expectedStep} of `)
    const progress = await progressLabel.innerText()
    const match = progress.match(/Step (\d+) of (\d+)/)
    expect(match).not.toBeNull()
    expect(Number(match![1])).toBe(expectedStep)
    total = Number(match![2])
    guidance.push(`${await popover(page).locator('.driver-popover-title').innerText()} ${await popover(page).locator('.driver-popover-description').innerText()}`)
    const active = page.locator('main .driver-active-element')
    if (await active.count()) {
      // Rapid movement must not leave earlier spotlight classes on the page.
      await expect(active).toHaveCount(1)
      await expect(active).toBeVisible()
      await expect(page.locator('[hidden].driver-active-element, [hidden] .driver-active-element')).toHaveCount(0)
      anchored += 1
    }
    if (options.viewportWidth) {
      const box = await popover(page).boundingBox()
      expect(box).not.toBeNull()
      expect(box!.x).toBeGreaterThanOrEqual(-1)
      expect(box!.x + box!.width).toBeLessThanOrEqual(options.viewportWidth + 1)
      expect(box!.y).toBeGreaterThanOrEqual(-1)
      expect(box!.y + box!.height).toBeLessThanOrEqual(741)
    }
    const finish = popover(page).getByRole('button', { name: 'Finish', exact: true })
    if (await finish.count()) {
      expect(expectedStep).toBe(total)
      await finish.click()
      break
    }
    await popover(page).getByRole('button', { name: 'Next', exact: true }).click()
    expectedStep += 1
  }
  await expect(popover(page)).toHaveCount(0)
  await expect(page.locator('.driver-overlay')).toHaveCount(0)
  return { anchored, total, guidance: guidance.join(' ') }
}

test('licence orientation explains the workflow, completes and replays on a pack deep link', async ({ page }) => {
  const mutations = await mockWorkspace(page)
  const url = '/licence-applications?application=synthetic-pack&tab=approval'
  const tourId = 'licences'
  await page.goto(url)
  await expect(page.getByRole('heading', { name: 'Pack readiness', exact: true })).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  const completed = await walkTour(page)
  expect(completed.total).toBeGreaterThanOrEqual(4)
  expect(completed.total).toBeLessThanOrEqual(6)
  expect(completed.anchored).toBeGreaterThanOrEqual(2)
  expect(completed.guidance).toMatch(/internal approval/i)
  expect(completed.guidance).toMatch(/authority/i)
  expect(await storedState(page, tourId)).toEqual({ status: 'completed', step: completed.total - 1 })
  await expect(page).toHaveURL(url)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Pack readiness', exact: true })).toBeVisible()
  await expect(invitation(page)).toHaveCount(0)
  await replay(page)
  await expect(popover(page)).toContainText(/Step 1 of/)
  // Rapid keyboard movement must settle on one spotlight, including during initial motion.
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('ArrowRight')
  await expect(popover(page)).toContainText(/Step [2-6] of/)
  await expect(page.locator('.driver-active-element')).toHaveCount(1)
  // The actual highlighted page control stays blocked during the orientation.
  const targetButton = page.locator('main .driver-active-element button:not(:disabled)').filter({ visible: true }).first()
  for (let index = 0; index < 4 && !await targetButton.count(); index += 1) {
    await popover(page).getByRole('button', { name: 'Next', exact: true }).click()
  }
  await expect(targetButton).toBeVisible()
  const bounds = await targetButton.boundingBox()
  expect(bounds).not.toBeNull()
  await page.mouse.click(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2)
  await expect(page).toHaveURL(url)
  await page.keyboard.press('Escape')
  expect(mutations).toEqual([])
})

test('licence orientation decisions follow its tabs and remain independent of certifications', async ({ page }) => {
  const mutations = await mockWorkspace(page)
  await page.goto('/licence-applications?application=synthetic-pack')
  await expect(invitation(page)).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Not now' }).click()
  expect(await storedState(page, 'licences')).toMatchObject({ status: 'dismissed' })
  await page.getByRole('navigation', { name: 'Licence pack sections' }).getByRole('button', { name: 'Forms and documents', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Forms and documents', exact: true })).toBeVisible()
  await expect(invitation(page)).toHaveCount(0)
  await replay(page)
  expect((await walkTour(page)).anchored).toBeGreaterThanOrEqual(2)
  expect(await storedState(page, 'licences')).toMatchObject({ status: 'completed' })
  const resources = page.getByRole('button', { name: 'Resources', exact: true }).filter({ visible: true })
  if (await resources.getAttribute('aria-expanded') === 'true') await resources.click()
  await page.getByRole('navigation', { name: 'Licence pack sections' }).getByRole('button', { name: 'Approval and submission', exact: true }).click()
  await expect(invitation(page)).toHaveCount(0)
  await page.goto('/certification-projects?project=synthetic-project')
  await expect(invitation(page)).toBeVisible()
  expect(await storedState(page, 'certifications')).toBeNull()
  expect(mutations).toEqual([])
})

test('certification orientation resumes explicitly after a tab change and refresh', async ({ page }) => {
  const mutations = await mockWorkspace(page)
  const url = '/certification-projects?project=synthetic-project&section=requirements'
  const tourId = 'certifications'
  await page.goto(url)
  await expect(page.getByRole('heading', { name: 'Project baseline', exact: true })).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await popover(page).getByRole('button', { name: 'Next', exact: true }).click()
  await expect(popover(page)).toContainText(/Step 2 of/)
  await page.evaluate(() => {
    history.pushState(null, '', '/certification-projects?project=synthetic-project&section=reports')
    dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(popover(page)).toHaveCount(0)
  await expect(invitation(page)).toBeVisible()
  expect(await storedState(page, tourId)).toEqual({ status: 'interrupted', step: 1 })
  await page.getByRole('navigation', { name: 'Project sections' }).getByRole('button', { name: 'Requirements and evidence', exact: true }).click()
  await expect(invitation(page).getByRole('button', { name: 'Resume product tour' })).toBeVisible()
  await page.reload()
  await expect(popover(page)).toHaveCount(0)
  await invitation(page).getByRole('button', { name: 'Resume product tour' }).click()
  await walkTour(page, { firstStep: 1 })
  expect(await storedState(page, tourId)).toMatchObject({ status: 'completed' })
  expect(mutations).toEqual([])
})

for (const width of [320, 390]) {
  test(`certification orientation fits ${width}px with reduced motion and preserves unsaved inputs`, async ({ page }) => {
    const mutations = await mockWorkspace(page)
    await page.setViewportSize({ width, height: 740 })
    await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' })
    const url = '/certification-projects?project=synthetic-project&section=testing'
    await page.goto(url)
    const provider = page.getByRole('textbox', { name: /Test lab or assurance provider/i })
    await provider.fill('Synthetic unsaved provider')
    await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
    await expect(popover(page)).toBeVisible()
    await expect(page.getByTestId('mobile-nav-drawer')).toHaveCount(0)
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => !!document.activeElement?.closest('.cap-product-tour'))).toBe(true)
    expect((await walkTour(page, { viewportWidth: width })).anchored).toBeGreaterThanOrEqual(2)
    await expect(provider).toHaveValue('Synthetic unsaved provider')
    await expect(page).toHaveURL(url)
    expect(mutations).toEqual([])
  })
}

test('conditional and unavailable licence targets still leave a complete usable tour', async ({ page }) => {
  const mutations = await mockWorkspace(page, { summaryAccess: true })
  const url = '/licence-applications?application=synthetic-pack&tab=approval'
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(url)
  await expect(page.getByText('You have summary access.', { exact: false })).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await walkTour(page)
  expect(errors).toEqual([])
  expect(mutations).toEqual([])
})

test('a failed licence load can still explain the section without changing records', async ({ page }) => {
  const mutations = await mockWorkspace(page, { packFailure: true })
  const url = '/licence-applications?application=synthetic-pack&tab=approval'
  await page.goto(url)
  await expect(page.getByText('Application could not be loaded.', { exact: false })).toBeVisible({ timeout: 15_000 })
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await walkTour(page)
  await expect(page).toHaveURL(url)
  expect(mutations).toEqual([])
})

test('library navigation selects and persists independent templates and evidence tours', async ({ page }) => {
  const mutations = await mockWorkspace(page)
  const templates = 'templates'
  const evidence = 'evidence'
  await page.goto('/library?section=templates')
  await expect(invitation(page)).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Not now' }).click()
  await page.getByRole('navigation', { name: 'Resource sections' }).getByRole('button', { name: 'Evidence', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Evidence', exact: true })).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  expect((await walkTour(page)).anchored).toBeGreaterThanOrEqual(1)
  expect(await storedState(page, evidence)).toMatchObject({ status: 'completed' })
  expect(await storedState(page, templates)).toMatchObject({ status: 'dismissed' })
  expect(mutations).toEqual([])
})


test('a failed lazy tour download restores the page and resumes after refresh', async ({ page }) => {
  const mutations = await mockWorkspace(page)
  let blocked = 0
  const driverModule = /\/driver__js\.js(?:\?|$)/
  await page.route(driverModule, async route => { blocked += 1; await route.abort('failed') })
  const url = '/licence-applications?application=synthetic-pack&tab=approval'
  await page.goto(url)
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await expect(page.getByText('The product tour could not start.', { exact: false })).toBeVisible()
  expect(blocked).toBeGreaterThan(0)
  await expect(popover(page)).toHaveCount(0)
  await expect(page.locator('.driver-overlay')).toHaveCount(0)
  await expect(invitation(page).getByRole('button', { name: 'Resume product tour' })).toBeVisible()
  await expect(page).toHaveURL(url)
  await page.unroute(driverModule)
  await page.reload()
  await invitation(page).getByRole('button', { name: 'Resume product tour' }).click()
  await walkTour(page)
  expect(await storedState(page, 'licences')).toMatchObject({ status: 'completed' })
  expect(mutations).toEqual([])
})


test('certification orientation explains its principles without changing a blocked package', async ({ page }) => {
  const mutations = await mockWorkspace(page, { includePackage: true })
  const url = '/certification-projects?project=synthetic-project&section=reports'
  await page.goto(url)
  await expect(page.getByRole('heading', { name: 'Readiness for synthetic-v1' })).toBeVisible()
  const requestApproval = page.getByRole('button', { name: 'Request approval', exact: true })
  await expect(requestApproval).toBeDisabled()
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  const completed = await walkTour(page)
  expect(completed.total).toBeGreaterThanOrEqual(4)
  expect(completed.total).toBeLessThanOrEqual(6)
  expect(completed.anchored).toBeGreaterThanOrEqual(2)
  expect(completed.guidance).toMatch(/approved requirement/i)
  expect(completed.guidance).toMatch(/provider|testing/i)
  expect(completed.guidance).toMatch(/authority|external/i)
  await expect(requestApproval).toBeDisabled()
  await expect(page.getByText('Synthetic submission assessment still needs closure.', { exact: true })).toBeVisible()
  expect(await storedState(page, 'certifications')).toMatchObject({ status: 'completed' })
  await expect(page).toHaveURL(url)
  expect(mutations).toEqual([])
})
