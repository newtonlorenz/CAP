import { expect, test, type Locator, type Page } from '@playwright/test'
import { loginAsAdmin as submitAdminLogin } from './testCredentials'

const MOBILE_VIEWPORT = { width: 320, height: 740 }
const TABLET_VIEWPORT = { width: 768, height: 1024 }

const routeChecks: Array<{ path: string; heading: RegExp }> = [
  { path: '/', heading: /Compliance Dashboard/i },
  { path: '/requirements', heading: /^Requirements$/i },
  { path: '/review-cycles', heading: /^Assessment overview$/i },
  { path: '/library?section=templates', heading: /^Form templates$/i },
  { path: '/access-teams', heading: /^Teams$/i },
  { path: '/licence-applications', heading: /^Licence packs$/i },
  { path: '/certification-projects', heading: /^Certifications$/i },
  { path: '/change-management', heading: /^Change Management$/i },
  { path: '/reports', heading: /^Reports$/i },
  { path: '/admin/users', heading: /^User Management$/i },
  { path: '/change-notes', heading: /^Change notes$/i },
]

const loginAsAdmin = async (page: Page) => {
  await submitAdminLogin(page)
  await page.waitForURL('/')
  await expect(page.getByRole('heading', { name: /Compliance Dashboard/i })).toBeVisible()
}

const assertNoHorizontalOverflow = async (page: Page) => {
  await page.evaluate(() => document.fonts.ready)
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }))
  const overflowing = scrollWidth > innerWidth ? await page.locator('main').evaluate(main => Array.from(main.querySelectorAll('*')).filter(node => node.getBoundingClientRect().right > window.innerWidth + 1).slice(0, 12).map(node => ({ tag: node.tagName, class: node.getAttribute('class'), text: node.textContent?.slice(0, 70) }))) : []
  expect(scrollWidth, JSON.stringify({ url: page.url(), overflowing })).toBeLessThanOrEqual(innerWidth)
}

const openRequirementsDocument = async (page: Page) => {
  await page.getByRole('heading', { name: /^Requirements$/i }).waitFor()

  await page.waitForFunction(() => {
    const hasRows = document.querySelectorAll('table tbody tr').length > 0
    const hasCards =
      document.querySelectorAll('[data-testid="requirements-sets-mobile-cards"] > *').length > 0
    const hasEmpty = (document.body.textContent || '').includes('No requirement sets available.')
    return hasRows || hasCards || hasEmpty
  })

  const preferredOpen = page.getByRole('link', { name: /^Open\s+E2E Document/i }).first()
  if ((await preferredOpen.count()) > 0) {
    await preferredOpen.click()
    await page.waitForURL(/\/requirements\/sets\//)
    return
  }

  const anyOpen = page.getByRole('link', { name: /^Open\s+/i }).first()
  if ((await anyOpen.count()) > 0) {
    await anyOpen.click()
    await page.waitForURL(/\/requirements\/sets\//)
    return
  }

  const preferredImport = page.getByRole('link', { name: /^Import\s+E2E Document/i }).first()
  if ((await preferredImport.count()) > 0) {
    await preferredImport.click()
    await page.waitForURL(/\/requirements\/sets\//)
    return
  }

  const anyImport = page.getByRole('link', { name: /^Import\s+/i }).first()
  if ((await anyImport.count()) > 0) {
    await anyImport.click()
    await page.waitForURL(/\/requirements\/sets\//)
    return
  }

  const anySetLink = page.locator('table tbody tr a:visible').first()
  await anySetLink.click()
  await page.waitForURL(/\/requirements\/sets\//)
}

const openFirstReviewCycle = async (page: Page): Promise<boolean> => {
  await page.goto('/review-cycles?status=active')
  await page.getByRole('heading', { name: /^Assessment overview$/i }).waitFor()
  await expect(page.getByTestId('review-cycles-mobile-cards')).toBeVisible()

  await page.waitForFunction(() => {
    const cards = document.querySelectorAll('[data-testid="review-cycles-mobile-cards"] > div')
    const hasCard = Array.from(cards).some((el) => el.querySelector('h2'))
    const hasEmpty = (document.body.textContent || '').includes('No assessments found.')
    return hasCard || hasEmpty
  })

  const hasEmptyState = await page.getByText('No assessments found.', { exact: false }).count()
  if (hasEmptyState > 0) {
    return false
  }

  const firstCard = page
    .locator('[data-testid="review-cycles-mobile-cards"] > div')
    .filter({ has: page.locator('h2') })
    .first()
  await firstCard.click()
  await page.waitForURL(/\/review-cycles\/[^/]+/)
  return true
}

const labelX = async (page: Page, text: RegExp): Promise<number> => {
  const locator = page.locator('label', { hasText: text }).last()
  await expect(locator).toBeVisible()
  const box = await locator.boundingBox()
  if (!box) {
    throw new Error(`Unable to determine label position for ${text.toString()}`)
  }
  return box.x
}

const labelY = async (page: Page, text: RegExp): Promise<number> => {
  const locator = page.locator('label', { hasText: text }).last()
  await expect(locator).toBeVisible()
  const box = await locator.boundingBox()
  if (!box) {
    throw new Error(`Unable to determine label position for ${text.toString()}`)
  }
  return box.y
}

const locatorY = async (locator: Locator, name: string): Promise<number> => {
  await expect(locator).toBeVisible()
  const box = await locator.boundingBox()
  if (!box) {
    throw new Error(`Unable to determine position for ${name}`)
  }
  return box.y
}

test.describe('Responsive Layout', () => {
  for (const viewport of [MOBILE_VIEWPORT, TABLET_VIEWPORT]) {
    test(`should keep routed pages within viewport at ${viewport.width}px`, async ({ page }, info) => {
      await page.setViewportSize(viewport)
      await loginAsAdmin(page)

      for (const route of routeChecks) {
        await page.goto(route.path)
        await expect(page.getByRole('heading', { name: route.heading, level: 1 })).toBeVisible()
        if (route.path === '/') {
          const insightsToggle = page.getByRole('button', { name: /more insights/i })
          if ((await insightsToggle.count()) > 0) {
            await insightsToggle.click()
          }
        }
        if (route.path === '/change-notes') {
          await expect(page.getByText('Current version', { exact: true })).toBeVisible()
          const previous = page.locator('summary').filter({ hasText: 'Version 2026.10.02' })
          await page.screenshot({ path: info.outputPath(`change-notes-${viewport.width}.png`), fullPage: true })
          await previous.click()
          await expect(page.getByRole('heading', { name: 'Profile and account settings', exact: true })).toBeVisible()
        }
        await assertNoHorizontalOverflow(page)
      }
    })
  }

  test('should open and close the mobile drawer navigation at 320px', async ({ page }) => {
    await page.setViewportSize(MOBILE_VIEWPORT)
    await loginAsAdmin(page)

    const toggle = page.getByTestId('mobile-nav-toggle')
    const drawer = page.getByTestId('mobile-nav-drawer')

    await expect(toggle).toBeVisible()
    await toggle.click()
    await expect(drawer).toBeVisible()

    await drawer.getByRole('link', { name: 'Reports' }).click()
    await page.waitForURL('/reports')
    await expect(page.getByTestId('mobile-nav-drawer')).toHaveCount(0)
    await assertNoHorizontalOverflow(page)
  })

  test('should render mobile card layouts on table-heavy pages at 320px', async ({ page }) => {
    await page.setViewportSize(MOBILE_VIEWPORT)
    await loginAsAdmin(page)

    await page.goto('/review-cycles')
    await expect(page.getByTestId('review-cycles-mobile-cards')).toBeVisible()
    await assertNoHorizontalOverflow(page)

    await page.goto('/admin/users')
    await expect(page.getByTestId('users-mobile-cards')).toBeVisible()
    await assertNoHorizontalOverflow(page)

    await page.goto('/requirements')
    await expect(page.getByTestId('requirements-sets-mobile-cards')).toBeVisible()
    await openRequirementsDocument(page)
    const library = page.getByRole('button', { name: 'Requirement library', exact: true })
    await library.click()
    await expect(page.getByTestId('requirements-view-mobile-cards')).toBeVisible()
    await assertNoHorizontalOverflow(page)
  })

  test('keeps review detail fields usable on mobile and desktop', async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await loginAsAdmin(page)

    const opened = await openFirstReviewCycle(page)
    test.skip(!opened, 'No review cycles available for responsive detail assertions.')

    const requirementMobileX = await labelX(page, /^Requirement Status$/i)
    const responsibleMobileX = await labelX(page, /^Responsible owner$/i)
    expect(Math.abs(requirementMobileX - responsibleMobileX)).toBeLessThan(8)

    const reviewMobileX = await labelX(page, /^Reviewer decision$/i)
    const assignedMobileX = await labelX(page, /^Assigned Reviewer$/i)
    expect(Math.abs(reviewMobileX - assignedMobileX)).toBeLessThan(8)

    const requirementY = await labelY(page, /^Requirement Status$/i)
    const evidenceY = await labelY(page, /^Evidence$/i)
    const commentsY = await locatorY(
      page.locator('summary', { hasText: /^Comments\s*\d+/i }).last(),
      'Comments section'
    )
    const reviewY = await labelY(page, /^Reviewer decision$/i)

    expect(requirementY).toBeLessThan(evidenceY)
    const jiraLabel = page.locator('label', { hasText: /^Jira Issue Key$/i }).last()
    if ((await jiraLabel.count()) > 0) {
      const jiraY = await locatorY(jiraLabel, 'Jira Issue Key')
      expect(evidenceY).toBeLessThan(jiraY)
      expect(jiraY).toBeLessThan(commentsY)
    } else {
      expect(evidenceY).toBeLessThan(commentsY)
    }
    expect(reviewY).toBeLessThan(evidenceY)

    const discussion = page.locator('.review-discussion').first()
    const discussionToggle = discussion.locator('summary')
    const comment = discussion.getByRole('textbox', { name: /^Comment on/ })
    await expect(comment).toBeHidden()
    await discussionToggle.focus()
    await page.keyboard.press('Enter')
    await comment.fill('Review draft retained while reading the requirement')
    await discussionToggle.click()
    await expect(comment).toBeHidden()
    await discussionToggle.click()
    await expect(comment).toHaveValue('Review draft retained while reading the requirement')
    await comment.fill('')

    await page.getByRole('button', { name: 'Filters and view options', exact: true }).click()
    await page.getByRole('button', { name: 'Focus on one requirement', exact: true }).click()
    await expect(page.locator('[id^="review-item-"]')).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Assessment overview', exact: true })).toBeVisible()
    await assertNoHorizontalOverflow(page)
    await page.screenshot({ path: info.outputPath('focused-review-mobile.png'), fullPage: true })

    await page.setViewportSize({ width: 1366, height: 900 })

    await expect(page.getByRole('combobox', { name: /^Requirement status for/ }).first()).toBeVisible()
    await expect(page.getByRole('combobox', { name: /^Responsible owner for/ }).first()).toBeVisible()
    await expect(page.getByRole('combobox', { name: /^Reviewer decision for/ }).first()).toBeVisible()
    await assertNoHorizontalOverflow(page)
    await page.screenshot({ path: info.outputPath('focused-review-desktop.png'), fullPage: true })
    await page.getByRole('button', { name: 'Assessment overview', exact: true }).click()
    await expect(page.getByRole('region', { name: 'Review readiness', exact: true })).toBeVisible()
  })
})

for (const colorScheme of ['light', 'dark'] as const) {
  for (const viewport of [{ width: 1440, height: 1000 }, MOBILE_VIEWPORT]) {
    test(`resource navigation and creation view: ${colorScheme} ${viewport.width}px`, async ({ page }, info) => {
      await page.setViewportSize(viewport)
      await page.emulateMedia({ colorScheme })
      await loginAsAdmin(page)
      await page.goto('/library?section=templates&returnTo=%2Fcertification-projects')
      await expect(page.getByRole('heading', { name: 'Form templates', exact: true })).toBeVisible()
      await expect(page.getByRole('navigation', { name: 'Library sections' })).toHaveCount(0)
      await expect(page.getByRole('link', { name: 'Return to your workspace' })).toHaveAttribute('href', '/certification-projects')
      if (viewport.width < 1024) await page.getByRole('button', { name: 'Toggle navigation' }).click()
      const nav = page.locator('nav[aria-label="Primary navigation"]:visible')
      await expect(nav.getByRole('link', { name: 'Form templates', exact: true })).toHaveAttribute('aria-current', 'page')
      await nav.getByRole('link', { name: 'Evidence', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Evidence', exact: true }).first()).toBeVisible()
      await assertNoHorizontalOverflow(page)
      await page.screenshot({ path: info.outputPath('resource.png'), fullPage: true })
      await page.goto('/licence-applications')
      await expect(page.getByLabel('Pack name', { exact: true })).toHaveCount(0)
      await page.getByRole('button', { name: 'New licence pack', exact: true }).click()
      await expect(page).toHaveURL(/create=1/)
      await expect(page.getByLabel('Pack name', { exact: true })).toBeVisible()
      await assertNoHorizontalOverflow(page)
      await page.screenshot({ path: info.outputPath('new-pack.png'), fullPage: true })
      await page.getByRole('button', { name: 'Cancel and return to applications' }).click()
      await expect(page.getByLabel('Pack name', { exact: true })).toHaveCount(0)
    })
  }
}
