import { expect, test, type Page } from '@playwright/test'

const userId = 'synthetic-onboarding-user'
const storageKey = (id = userId) => `cap:product-tour:v1:${encodeURIComponent(id)}`
const invitation = (page: Page) => page.getByRole('region', { name: 'Product tour invitation' })
const popover = (page: Page) => page.locator('.cap-product-tour')

async function mockAccount(page: Page) {
  let activeUser: string | null = userId
  let profileName = 'Synthetic Tour User'
  let notifications = { review_mentions: true, review_reminders: false }
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    if (path === '/auth/logout') activeUser = null
    if (path === '/auth/login') activeUser = route.request().postDataJSON().email.startsWith('second') ? 'second-user' : userId
    if (path === '/auth/me') {
      if (route.request().method() === 'PATCH') profileName = route.request().postDataJSON().full_name
      await route.fulfill({ status: activeUser ? 200 : 401, json: activeUser ? {
        id: activeUser, organization_id: 'synthetic-organisation', full_name: profileName,
        email: `${activeUser}@example.test`, role: 'admin', active: true, created_at: '2026-01-01T00:00:00Z',
      } : { detail: 'Not authenticated' } })
      return
    }
    if (path === '/auth/notification-settings' && route.request().method() === 'PATCH') notifications = route.request().postDataJSON()
    if (path === '/auth/refresh' && !activeUser) {
      await route.fulfill({ status: 401, json: { detail: 'Not authenticated' } })
      return
    }
    await route.fulfill({ json: path === '/product-feedback/config' ? { enabled: false }
      : path === '/auth/notification-settings' ? notifications
        : { items: [], total: 0, limit: 1000, offset: 0 } })
  })
}

async function storedState(page: Page, id = userId) {
  return page.evaluate(key => JSON.parse(localStorage.getItem(key) || 'null'), storageKey(id))
}

async function replay(page: Page) {
  if ((await page.viewportSize())!.width < 1280) await page.getByTestId('mobile-nav-toggle').click()
  else if (await page.getByRole('button', { name: 'Resources', exact: true }).getAttribute('aria-expanded') !== 'true') await page.getByRole('button', { name: 'Resources', exact: true }).click()
  await page.getByRole('button', { name: 'Product tour', exact: true }).filter({ visible: true }).click()
  await expect(popover(page)).toBeVisible()
}

async function assertSpotlightWithinNavigation(page: Page, step = 1) {
  const targetName = ['requirements', 'assessment', 'evidence', 'reports'][step - 1]
  const target = page.locator(`[data-testid="primary-nav"] [data-tour="${targetName}"]`)
  if (!await target.count() || !await target.isVisible()) return
  // Driver changes popover text before finishing the animated spotlight transition.
  await expect(target).toHaveClass(/driver-active-element/)
  const bounds = await target.evaluate(element => {
    const targetBounds = element.getBoundingClientRect()
    const labelBounds = element.querySelector('span')!.getBoundingClientRect()
    const panelBounds = element.closest('#resource-navigation')!.getBoundingClientRect()
    return { top: targetBounds.top, bottom: targetBounds.bottom, labelTop: labelBounds.top, labelBottom: labelBounds.bottom, clipTop: Math.max(0, panelBounds.top), clipBottom: Math.min(window.innerHeight, panelBounds.bottom), left: targetBounds.left, right: targetBounds.right, width: window.innerWidth }
  })
  expect(bounds.top).toBeGreaterThanOrEqual(bounds.clipTop - 1)
  expect(bounds.bottom).toBeLessThanOrEqual(bounds.clipBottom + 1)
  expect(bounds.labelTop).toBeGreaterThanOrEqual(bounds.clipTop - 1)
  expect(bounds.labelBottom).toBeLessThanOrEqual(bounds.clipBottom + 1)
  expect(bounds.left).toBeGreaterThanOrEqual(0)
  expect(bounds.right).toBeLessThanOrEqual(bounds.width)
}

async function finishTour(page: Page, firstStep = 1) {
  for (let step = firstStep; step <= 4; step++) {
    await expect(popover(page)).toContainText(`Step ${step} of 4`)
    await assertSpotlightWithinNavigation(page, step)
    await popover(page).getByRole('button', { name: step === 4 ? 'Finish' : 'Next', exact: true }).click()
  }
  await expect(popover(page)).toHaveCount(0)
  await expect(page.locator('.driver-overlay')).toHaveCount(0)
}

test.beforeEach(async ({ page }) => { await mockAccount(page) })

test('invites without changing a deep link or stealing focus, completes and replays', async ({ page }, info) => {
  await page.goto('/guide?topic=evidence#overview')
  await expect(invitation(page)).toBeVisible()
  await expect(page).toHaveURL('/guide?topic=evidence#overview')
  await expect(popover(page)).toHaveCount(0)
  expect(await page.evaluate(() => document.activeElement?.closest('[aria-label="Product tour invitation"]') !== null)).toBe(false)
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await expect(page.locator('[data-tour="requirements"].driver-active-element')).toBeVisible()
  await popover(page).evaluate(async element => { await Promise.all(element.getAnimations().map(animation => animation.finished)) })
  await page.screenshot({ path: info.outputPath('tour-desktop-light.png') })
  await finishTour(page)
  expect(await storedState(page)).toMatchObject({ status: 'completed', step: 3 })
  await expect(page).toHaveURL('/guide?topic=evidence#overview')
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(invitation(page)).toHaveCount(0)
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveClass(/dark/)
  await replay(page)
  await expect(popover(page)).toContainText('Step 1 of 4')
  await popover(page).evaluate(async element => { await Promise.all(element.getAnimations().map(animation => animation.finished)) })
  const close = popover(page).getByRole('button', { name: 'Close product tour' })
  await close.focus()
  const titleColour = await popover(page).locator('.driver-popover-title').evaluate(element => getComputedStyle(element).color)
  await expect.poll(() => close.evaluate(element => getComputedStyle(element).color)).toBe(titleColour)
  const next = popover(page).getByRole('button', { name: 'Next', exact: true })
  await next.focus()
  expect(await next.evaluate(element => getComputedStyle(element).color)).toBe('rgb(255, 255, 255)')
  await close.focus()
  await assertSpotlightWithinNavigation(page)
  await page.screenshot({ path: info.outputPath('tour-desktop-dark.png') })
  await finishTour(page)
})

test('dismissal survives reload and remains isolated from another user', async ({ page }) => {
  await page.goto('/guide')
  await invitation(page).getByRole('button', { name: 'Not now' }).click()
  expect(await storedState(page)).toMatchObject({ status: 'dismissed' })
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(invitation(page)).toHaveCount(0)
  await page.getByRole('button', { name: 'Profile options' }).click()
  await page.getByRole('button', { name: 'Logout', exact: true }).click()
  await expect(page).toHaveURL('/login')
  await page.locator('input[type="email"]').fill('second@example.test')
  await page.locator('input[type="password"]').fill('synthetic-password-only')
  await page.locator('button[type="submit"]').click()
  await expect(invitation(page)).toBeVisible()
  expect(await storedState(page, 'second-user')).toBeNull()
  expect(await storedState(page)).toMatchObject({ status: 'dismissed' })
})

test('interruption saves progress and resumes explicitly after refresh', async ({ page }) => {
  await page.goto('/guide')
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await popover(page).getByRole('button', { name: 'Next', exact: true }).click()
  await expect(popover(page)).toContainText('Step 2 of 4')
  await page.reload()
  await expect(popover(page)).toHaveCount(0)
  await expect(invitation(page)).toContainText('Continue your product tour')
  await invitation(page).getByRole('button', { name: 'Resume product tour' }).click()
  await finishTour(page, 2)
})

test('keyboard controls keep focus in the tour and return focus after Escape', async ({ page }) => {
  await page.goto('/guide')
  await invitation(page).getByRole('button', { name: 'Not now' }).click()
  await page.getByRole('button', { name: 'Resources', exact: true }).click()
  const replayButton = page.getByRole('button', { name: 'Product tour', exact: true }).filter({ visible: true })
  await replayButton.focus()
  await page.keyboard.press('Enter')
  await expect(popover(page)).toBeVisible()
  await page.keyboard.press('ArrowLeft')
  await expect(popover(page)).toContainText('Step 1 of 4')
  for (let index = 0; index < 8; index++) {
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => !!document.activeElement?.closest('.cap-product-tour'))).toBe(true)
  }
  await page.keyboard.press('ArrowRight')
  await expect(popover(page)).toContainText('Step 2 of 4')
  await page.keyboard.press('ArrowLeft')
  await expect(popover(page)).toContainText('Step 1 of 4')
  await page.keyboard.press('Shift+Tab')
  expect(await page.evaluate(() => !!document.activeElement?.closest('.cap-product-tour'))).toBe(true)
  await page.keyboard.press('Escape')
  await expect(popover(page)).toHaveCount(0)
  await expect(replayButton).toBeFocused()
  await replay(page)
  for (let step = 1; step <= 4; step++) {
    await expect(popover(page)).toContainText(`Step ${step} of 4`)
    await page.keyboard.press('ArrowRight')
  }
  await expect(popover(page)).toHaveCount(0)
  expect(await storedState(page)).toMatchObject({ status: 'completed', step: 3 })
})

for (const width of [320, 390]) {
  test(`mobile tour works at ${width}px with reduced motion and drawer replay`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 740 })
    await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' })
    await page.goto('/guide?topic=forms')
    await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
    await expect(popover(page)).toBeVisible()
    await expect(page.getByTestId('mobile-nav-drawer')).toHaveCount(0)
    for (let step = 1; step <= 4; step++) {
      await expect(popover(page)).toContainText(`Step ${step} of 4`)
      const box = await popover(page).boundingBox()
      expect(box).not.toBeNull()
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1)
      expect(box!.y + box!.height).toBeLessThanOrEqual(741)
      if (step === 1) await page.screenshot({ path: info.outputPath(`tour-mobile-${width}.png`) })
      await popover(page).getByRole('button', { name: step === 4 ? 'Finish' : 'Next', exact: true }).click()
    }
    await expect(page).toHaveURL('/guide?topic=forms')
    await replay(page)
    await expect(page.getByTestId('mobile-nav-drawer')).toHaveCount(0)
    expect(await page.evaluate(() => !!document.querySelector('main')?.closest('[inert]'))).toBe(false)
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => !!document.activeElement?.closest('.cap-product-tour'))).toBe(true)
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('mobile-nav-toggle')).toBeFocused()
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe('hidden')
  })
}

test('resize and navigation clean up overlays and allow resuming', async ({ page }) => {
  await page.goto('/guide')
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await expect(popover(page)).toBeVisible()
  await page.setViewportSize({ width: 1180, height: 844 })
  await expect(popover(page)).toHaveCount(0)
  await invitation(page).getByRole('button', { name: 'Resume product tour' }).click()
  await expect(popover(page)).toBeVisible()
  await expect(page.locator('[data-tour].driver-active-element')).toHaveCount(0)
  await page.evaluate(() => { history.pushState(null, '', '/change-notes'); dispatchEvent(new PopStateEvent('popstate')) })
  await expect(page).toHaveURL('/change-notes')
  await expect(popover(page)).toHaveCount(0)
  await expect(page.locator('.driver-overlay')).toHaveCount(0)
  await expect(invitation(page)).toContainText('Continue your product tour')
})

test('missing desktop target falls back to usable steps', async ({ page }) => {
  await page.addInitScript(() => {
    new MutationObserver(() => document.querySelectorAll('#resource-navigation [data-tour="requirements"]').forEach(node => node.remove())).observe(document, { childList: true, subtree: true })
  })
  await page.goto('/guide')
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await expect(page.locator('[data-tour="requirements"].driver-active-element')).toHaveCount(0)
  await finishTour(page)
})

test('hidden desktop targets fall back to usable floating steps', async ({ page }) => {
  await page.goto('/guide')
  await page.addStyleTag({ content: '#resource-navigation [data-tour="requirements"] { display: none; } #resource-navigation [data-tour="assessment"] { visibility: hidden; }' })
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await expect(page.locator('[data-tour="requirements"].driver-active-element')).toHaveCount(0)
  await popover(page).getByRole('button', { name: 'Next', exact: true }).click()
  await expect(popover(page)).toContainText('Step 2 of 4')
  await expect(page.locator('[data-tour="assessment"].driver-active-element')).toHaveCount(0)
  await finishTour(page, 2)
})

test('quick close during animation preserves Resources state and replay', async ({ page }) => {
  await page.goto('/guide')
  const resources = page.getByRole('button', { name: 'Resources', exact: true })
  await expect(resources).toHaveAttribute('aria-expanded', 'false')
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await popover(page).getByRole('button', { name: 'Close product tour' }).click()
  await expect(popover(page)).toHaveCount(0)
  await expect(resources).toHaveAttribute('aria-expanded', 'false')
  await expect(resources).toBeFocused()
  await replay(page)
  await expect(popover(page)).toBeVisible()
  await page.locator('.driver-overlay').click({ position: { x: 1100, y: 40 } })
  await expect(popover(page)).toHaveCount(0)
  await expect(resources).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByRole('button', { name: 'Product tour', exact: true })).toBeEnabled()
})

test('corrupt and blocked storage do not stop the app or tour', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(key => localStorage.setItem(key, '{invalid'), storageKey())
  await page.goto('/guide')
  await expect(invitation(page)).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await finishTour(page)
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw new DOMException('Storage unavailable', 'SecurityError') } })
  })
  await page.reload()
  await expect(invitation(page)).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await finishTour(page)
  expect(errors).toEqual([])
})

test('invitation and tour preserve an unsaved account form', async ({ page }) => {
  await page.goto('/account?section=account')
  const fullName = page.getByRole('textbox', { name: 'Full name' })
  await fullName.fill('Synthetic unsaved name')
  await expect(fullName).toBeFocused()
  await expect(invitation(page)).toBeVisible()
  await expect(page).toHaveURL('/account?section=account')
  await page.getByRole('heading', { name: 'My account', exact: true }).click()
  await expect(invitation(page)).toBeVisible()
  await invitation(page).getByRole('button', { name: 'Start product tour' }).click()
  await finishTour(page)
  await expect(fullName).toHaveValue('Synthetic unsaved name')
  await expect(page).toHaveURL('/account?section=account')
})

test('typing, single save clicks, and checkbox focus keep invitation geometry stable', async ({ page }) => {
  await page.goto('/account?section=account')
  await expect(invitation(page)).toBeVisible()
  const invitationBounds = await invitation(page).boundingBox()
  const fullName = page.getByRole('textbox', { name: 'Full name' })
  await fullName.fill('Synthetic saved name')
  await expect(fullName).toBeFocused()
  await expect(invitation(page)).toBeVisible()
  expect(await invitation(page).boundingBox()).toEqual(invitationBounds)
  const profileSaves: string[] = []
  page.on('request', request => {
    if (new URL(request.url()).pathname.endsWith('/auth/me') && request.method() === 'PATCH') profileSaves.push(request.postData() || '')
  })
  const saveProfile = page.getByRole('button', { name: 'Save profile', exact: true })
  const profileResponse = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/auth/me') && response.request().method() === 'PATCH')
  await saveProfile.click()
  expect((await profileResponse).ok()).toBe(true)
  await expect(saveProfile).toBeDisabled()
  await expect(fullName).toHaveValue('Synthetic saved name')
  expect(profileSaves).toHaveLength(1)
  expect(JSON.parse(profileSaves[0])).toMatchObject({ full_name: 'Synthetic saved name' })
  expect(await invitation(page).boundingBox()).toEqual(invitationBounds)

  await page.getByRole('button', { name: 'Notifications', exact: true }).click()
  await expect(invitation(page)).toBeVisible()
  const checkbox = page.getByRole('checkbox', { name: /review reminders/i })
  const notificationBounds = await invitation(page).boundingBox()
  await checkbox.check()
  await expect(checkbox).toBeChecked()
  expect(await invitation(page).boundingBox()).toEqual(notificationBounds)
  const notificationResponse = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/auth/notification-settings') && response.request().method() === 'PATCH')
  await page.getByRole('button', { name: 'Save notification settings', exact: true }).click()
  expect((await notificationResponse).ok()).toBe(true)
  await expect(page.getByRole('button', { name: 'Save notification settings', exact: true })).toBeDisabled()
  await expect(checkbox).toBeChecked()
})
