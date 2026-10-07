import { expect, test, type Page, type APIResponse } from '@playwright/test'
import { e2eAdminPassword, loginAsAdmin } from './testCredentials'

async function data(response: Pick<APIResponse, 'ok' | 'text' | 'json'>) {
  expect(response.ok(), await response.text()).toBeTruthy()
  return response.json()
}
async function jurisdiction(page: Page) {
  await expect(page.getByLabel('Jurisdiction selector').locator('option:checked')).toHaveText('Example jurisdiction')
  const options = await page.getByLabel('Jurisdiction selector').locator('option').evaluateAll(nodes => nodes.map(node => ({ value: (node as HTMLOptionElement).value, label: node.textContent })))
  return options.find(option => option.label === 'Example jurisdiction')!.value
}
test.beforeEach(async ({ page }) => {
  await loginAsAdmin(page)
  await page.waitForURL('/')
  const token = (await page.context().cookies()).find(cookie => cookie.name === 'csrf_token')
  expect(token).toBeDefined()
  await page.context().setExtraHTTPHeaders({ 'X-CSRF-Token': token!.value })
})

test('team member search preserves selections and saves without an unsaved-change prompt', async ({ page }) => {
  const suffix = Date.now()
  const people = []
  for (let index = 0; index < 16; index++) {
    people.push(await data(await page.request.post('/api/v1/users', { data: { email: `workflow-${suffix}-${index}@example.com`, password: e2eAdminPassword, full_name: `Workflow Person ${suffix}-${index}`, role: 'contributor' } })))
  }
  await page.goto('/access-teams')
  await page.getByRole('button', { name: 'New team', exact: true }).click()
  await page.getByLabel('Team name', { exact: true }).fill(`Workflow team ${suffix}`)
  const members = page.getByRole('group', { name: 'Choose team members' })
  expect(await members.evaluate(node => node.scrollHeight > node.clientHeight)).toBeTruthy()
  await page.getByRole('searchbox', { name: 'Find a person' }).fill(people[0].email)
  await page.getByRole('checkbox', { name: new RegExp(people[0].full_name) }).check()
  await page.getByRole('searchbox', { name: 'Find a person' }).fill(people[1].email)
  const secondMember = page.getByRole('checkbox', { name: new RegExp(people[1].full_name) })
  await secondMember.focus()
  await page.keyboard.press('Space')
  await expect(secondMember).toBeChecked()
  await expect(page.getByText('3 selected', { exact: true })).toBeVisible()
  const dialogs: string[] = []
  page.on('dialog', async dialog => { dialogs.push(dialog.type()); await dialog.dismiss() })
  const saved = page.waitForResponse(response => response.url().endsWith('/access/teams') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Create team', exact: true }).click()
  const team = await data(await saved)
  await expect(page).toHaveURL(new RegExp(`team=${team.id}`))
  await expect(page.getByRole('heading', { name: `Edit ${team.name}`, exact: true })).toBeVisible()
  const persisted = await data(await page.request.get('/api/v1/access/teams'))
  expect(persisted.find((item: { id: string }) => item.id === team.id).member_ids).toEqual(expect.arrayContaining([people[0].id, people[1].id]))
  expect(dialogs).toEqual([])
})

test('licence form completion stays in its application and separates acceptance from pack approval', async ({ page }) => {
  const jurisdictionId = await jurisdiction(page)
  const template = await data(await page.request.post('/api/v1/preparation/templates', { data: { name: 'Synthetic licence form', kind: 'licence_application', fields: [{ key: 'company', label: 'Company name', type: 'text', required: true }] } }))
  const application = await data(await page.request.post('/api/v1/applications', { data: { name: `Workflow application ${Date.now()}`, scope: 'annex_only', jurisdiction_id: jurisdictionId } }))
  const configured = await data(await page.request.post(`/api/v1/applications/${application.id}/components`, { data: { expected_revision: application.revision, name: 'Applicant annex', kind: 'annex', template_id: template.id } }))
  const formId = configured.components[0].case_id
  await page.goto(`/licence-applications?application=${application.id}&tab=approval`)
  await page.getByRole('button', { name: 'Review Company name', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`case=${formId}.*field=company`))
  await expect(page.locator('#preparation-field-company')).toBeFocused()
  await page.getByRole('textbox', { name: 'Company name', exact: true }).fill('Synthetic Applicant Ltd')
  await expect(page.getByRole('button', { name: 'Accept response', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Accept response', exact: true }).click()
  await expect(page.getByText('Accepted', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Return to pack' }).click()
  await expect(page.getByRole('heading', { name: application.name, exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approval and submission', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByText('Ready for internal approval', { exact: true })).toBeVisible()
  const current = await data(await page.request.get(`/api/v1/applications/${application.id}`))
  expect(current.status).toBe('draft')
  expect(current.snapshots).toHaveLength(0)
})

test('change reassessment and periodic work remain inside the certification context', async ({ page }) => {
  const jurisdictionId = await jurisdiction(page)
  const sets = await data(await page.request.get(`/api/v1/requirements/sets?jurisdiction_id=${jurisdictionId}`))
  const source = sets.items.find((item: { name: string }) => item.name === 'E2E Document')
  const project = await data(await page.request.post('/api/v1/certification-projects', { data: { name: `Workflow certification ${Date.now()}`, jurisdiction_id: jurisdictionId, requirement_set_ids: [source.document_id] } }))
  const versionId = project.baseline_versions[0].requirement_set_version_id
  const requirements = await data(await page.request.get(`/api/v1/requirements?requirement_set_version_id=${versionId}`))
  const registers = await data(await page.request.get(`/api/v1/change-management/registers?jurisdiction_id=${jurisdictionId}`))
  const register = registers.items[0] || await data(await page.request.post('/api/v1/change-management/registers', { data: { name: `Workflow register ${Date.now()}`, jurisdiction_id: jurisdictionId } }))
  const change = await data(await page.request.post(`/api/v1/change-management/registers/${register.id}/changes`, { data: { title: `Workflow change ${Date.now()}` } }))
  await data(await page.request.put(`/api/v1/change-management/changes/${change.id}/impacts`, { data: { items: [{ requirement_set_version_id: versionId, requirement_id: requirements.items[0].id, certification_project_id: project.id, rationale: 'Synthetic affected control' }] } }))
  await page.goto(`/change-management?change=${change.id}&tab=changes`)
  await page.getByRole('checkbox', { name: /^Assess / }).check()
  const created = page.waitForResponse(response => response.url().endsWith(`/changes/${change.id}/assessments`) && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Create assessment for selected impacts' }).click()
  const assessment = (await data(await created)).items[0]
  await page.getByRole('link', { name: assessment.name, exact: true }).click()
  await expect(page.getByRole('link', { name: 'Back to change', exact: true })).toBeVisible()
  expect((await data(await page.request.get(`/api/v1/review-cycles/${assessment.id}`))).items).toHaveLength(1)
  await page.goto(`/certification-projects?project=${project.id}&section=maintenance`)
  await page.getByText('Add maintenance plan', { exact: true }).click()
  await page.getByLabel('Plan name', { exact: true }).fill('Synthetic periodic assessment')
  await page.getByLabel('First due date', { exact: true }).fill(new Date(Date.now() - 86400000 * 2).toISOString().slice(0, 10))
  const savedPlan = page.waitForResponse(response =>
    response.url().endsWith('/maintenance-plans') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Add plan', exact: true }).click()
  const plan = await data(await savedPlan)
  expect(plan.name).toBe('Synthetic periodic assessment')
  expect(plan.certification_project_id).toBe(project.id)
  await expect(page.getByText('Synthetic periodic assessment', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Run due plans', exact: true }).click()
  await expect(page.getByText('1 maintenance assessments created for due plans in this project.', { exact: true })).toBeVisible()
  const cycles = await data(await page.request.get(`/api/v1/review-cycles?certification_project_id=${project.id}`))
  const maintenance = cycles.items.find((item: { cycle_type: string }) => item.cycle_type === 'maintenance')
  expect(maintenance.baseline_versions[0].requirement_set_version_id).toBe(versionId)
  expect(maintenance.certification_project_id).toBe(project.id)
})


test('shared workspaces remain usable in both themes on desktop and mobile', async ({ page }, info) => {
  const team = await data(await page.request.post('/api/v1/access/teams', { data: { name: `Theme team ${Date.now()}`, member_ids: [] } }))
  const routes = ['/library?section=templates', `/access-teams?team=${team.id}`, '/licence-applications', '/certification-projects', '/change-management']
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => localStorage.setItem('cap:theme', value), theme)
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 900 })
      for (const route of routes) {
        await page.goto(route)
        await expect(page.locator('main h1').first()).toBeVisible()
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
        if (route.startsWith('/access-teams')) {
          await expect(page.getByLabel('Team name', { exact: true })).toBeVisible()
          await page.screenshot({ path: info.outputPath(`teams-${theme}-${width}.png`), fullPage: true })
        } else if (route.startsWith('/library')) {
          await expect(page.getByRole('heading', { name: 'Form templates', exact: true })).toBeVisible()
          await expect(page.getByRole('navigation', { name: 'Library sections' })).toHaveCount(0)
          await expect(page.getByText('Loading templates…', { exact: true })).toHaveCount(0)
          await page.screenshot({ path: info.outputPath(`library-${theme}-${width}.png`), fullPage: true })
        }
      }
    }
  }
})
