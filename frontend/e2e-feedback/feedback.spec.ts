import { test, expect, type Page } from '@playwright/test'

async function login(page: Page, role = 'admin') {
  await page.goto('/login')
  await page.locator('input[type=email]').fill(`${role}@feedback.test`)
  await page.locator('input[type=password]').fill('Disposable feedback fixture 42!')
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Share product feedback' })).toBeVisible()
  await page.goto('/guide')
  await expect(page.locator('main h1')).toBeVisible()
}

test('real service: select an element, preview screenshot, submit and triage', async ({ page }) => {
  const failures: string[] = []
  page.on('pageerror', error => failures.push(error.message))
  await login(page)
  await page.getByRole('button', { name: 'Share product feedback' }).click()
  await page.getByLabel('Your feedback', { exact: true }).fill('The guide heading needs a clearer label.')
  await page.getByRole('button', { name: 'Point to something' }).click()
  await page.locator('main h1').click()
  const image = page.getByAltText('Screenshot attached to your feedback')
  await expect(image).toBeVisible({ timeout: 20000 })
  expect(await image.getAttribute('src')).toMatch(/^data:image\/jpeg;base64,/)
  await expect(page).toHaveURL(/\/guide$/)
  await page.screenshot({ path: 'test-results/feedback-light.png', animations: 'disabled' })
  await page.getByRole('button', { name: 'Close feedback' }).click()
  await page.getByRole('button', { name: 'Use dark theme' }).click()
  await page.getByRole('button', { name: 'Share product feedback' }).click()
  await page.screenshot({ path: 'test-results/feedback-dark.png', animations: 'disabled' })
  await page.getByRole('button', { name: 'Send feedback', exact: true }).click()
  await expect(page.getByText('Thanks for the feedback.')).toBeVisible()
  await page.getByRole('button', { name: 'Done', exact: true }).click()
  await page.goto('/admin/feedback')
  const report = page.getByRole('article').filter({ hasText: 'The guide heading needs a clearer label.' })
  await expect(report).toBeVisible()
  await report.getByRole('button', { name: 'View screenshot' }).click()
  await expect(report.getByRole('img')).toBeVisible()
  await expect.poll(() => report.getByRole('img').evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
  await report.getByRole('combobox').selectOption('done')
  await page.reload()
  await expect(page.getByRole('article').filter({ hasText: 'The guide heading needs a clearer label.' }).getByRole('combobox')).toHaveValue('done')
  expect(failures).toEqual([])
})

test('failed submission keeps the draft and uses the same id on retry', async ({ page }) => {
  await login(page)
  let firstId = ''
  let calls = 0
  await page.route('**/api/v1/product-feedback', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    calls++
    const id = route.request().postDataJSON().id
    if (calls === 1) {
      firstId = id
      // Accept upstream, then lose the browser response: exercise real service idempotency.
      await route.fetch()
      return route.abort()
    }
    expect(id).toBe(firstId)
    return route.continue()
  })
  await page.getByRole('button', { name: 'Share product feedback' }).click()
  await page.getByLabel('Your feedback', { exact: true }).fill('Retry this report exactly once.')
  await page.getByRole('button', { name: 'Send feedback', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Your draft is here')
  await expect(page.getByLabel('Your feedback', { exact: true })).toHaveValue('Retry this report exactly once.')
  await page.getByRole('button', { name: 'Send feedback', exact: true }).click()
  await expect(page.getByText('Thanks for the feedback.')).toBeVisible()
  await page.goto('/admin/feedback')
  await expect(page.getByRole('article').filter({ hasText: 'Retry this report exactly once.' })).toHaveCount(1)
})

test('selection never activates links; Escape cancels; navigation clears pin', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: 'Share product feedback' }).click()
  await page.getByRole('button', { name: 'Point to something' }).click()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: 'Share feedback' })).toBeVisible()
  await page.getByRole('button', { name: 'Point to something' }).click()
  await page.getByRole('link', { name: 'Dashboard', exact: true }).first().click()
  await expect(page.getByAltText('Screenshot attached to your feedback')).toBeVisible({ timeout: 20000 })
  await expect(page).toHaveURL(/\/guide$/)
  await page.getByRole('button', { name: 'Close feedback' }).click()
  await page.getByRole('link', { name: 'Dashboard', exact: true }).first().click()
  await page.getByRole('button', { name: 'Share product feedback' }).click()
  await expect(page.getByText('① Element selected')).toHaveCount(0)
  await expect(page.getByAltText('Screenshot attached to your feedback')).toHaveCount(0)
})

test('mobile feature request and non-admin access', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, 'contributor')
  await page.getByRole('button', { name: 'Share product feedback' }).click()
  await page.getByLabel('What would you like to share?').selectOption('feature')
  await page.getByLabel('Your feedback', { exact: true }).fill('Add a keyboard shortcut for the guide.')
  const bounds = await page.getByRole('dialog', { name: 'Share feedback' }).boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390)
  await page.screenshot({ path: 'test-results/feedback-mobile.png' })
  await page.getByRole('button', { name: 'Send feedback', exact: true }).click()
  await expect(page.getByText('Thanks for the feedback.')).toBeVisible()
  expect((await page.request.get('/api/v1/product-feedback')).status()).toBe(403)
  await page.getByRole('button', { name: 'Done', exact: true }).click()
  await page.getByRole('button', { name: 'Logout', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Share product feedback' })).toHaveCount(0)
})

test('capture hides private regions and form values without modifying the live page', async ({ page }) => {
  await login(page)
  await page.evaluate(() => {
    const wrapper = document.createElement('div')
    wrapper.id = 'capture-fixture'
    wrapper.innerHTML = '<div data-feedback-private style="position:fixed;left:280px;top:170px;width:80px;height:80px;background:red;z-index:55"><span style="visibility:visible">Private</span></div><div style="position:fixed;left:380px;top:170px;width:80px;height:80px;background:lime;z-index:55"></div><input id="private-input" value="Keep this value" style="position:fixed;left:480px;top:170px;width:80px;height:80px;background:magenta;z-index:55">'
    document.body.append(wrapper)
  })
  await page.getByRole('button', { name: 'Share product feedback' }).click()
  await page.getByRole('button', { name: 'Attach screenshot' }).click()
  const preview = page.getByAltText('Screenshot attached to your feedback')
  await expect(preview).toBeVisible({ timeout: 20000 })
  const pixels = await preview.evaluate(async (img: HTMLImageElement) => {
    await img.decode()
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth; canvas.height = img.naturalHeight
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(img, 0, 0)
    return [300, 400, 500].map(x => Array.from(ctx.getImageData(x, 200, 1, 1).data))
  })
  expect(pixels[0][1]).toBeGreaterThan(50) // The red private block has disappeared.
  expect(pixels[1][0]).toBeLessThan(50)
  expect(pixels[1][1]).toBeGreaterThan(200) // The public green block is captured.
  expect(pixels[2][1]).toBeGreaterThan(50) // The magenta input has disappeared.
  await expect(page.locator('#private-input')).toHaveValue('Keep this value')
  await expect(page.locator('#capture-fixture [data-feedback-private]')).toBeVisible()
})

test('capture preserves closed and open disclosure content', async ({ page }) => {
  await login(page)
  await page.evaluate(() => {
    const wrapper = document.createElement('div')
    wrapper.innerHTML = '<details id="closed-capture-fixture"><summary>Closed</summary><div style="position:fixed;left:280px;top:170px;width:80px;height:80px;background:red;z-index:55">Hidden</div></details><details id="open-capture-fixture" open><summary>Open</summary><div style="position:fixed;left:380px;top:170px;width:80px;height:80px;background:lime;z-index:55"></div></details>'
    document.body.append(wrapper)
  })
  await page.getByRole('button', { name: 'Share product feedback' }).click()
  await page.getByRole('button', { name: 'Attach screenshot' }).click()
  const preview = page.getByAltText('Screenshot attached to your feedback')
  await expect(preview).toBeVisible({ timeout: 20000 })
  const pixels = await preview.evaluate(async (img: HTMLImageElement) => {
    await img.decode()
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth; canvas.height = img.naturalHeight
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(img, 0, 0)
    return [300, 400].map(x => Array.from(ctx.getImageData(x, 200, 1, 1).data))
  })
  expect(pixels[0][1]).toBeGreaterThan(50)
  expect(pixels[1][0]).toBeLessThan(50)
  expect(pixels[1][1]).toBeGreaterThan(200)
  await expect(page.locator('#closed-capture-fixture')).not.toHaveAttribute('open')
  await expect(page.locator('#open-capture-fixture')).toHaveAttribute('open', '')
})
