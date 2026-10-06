import { test, expect } from '@playwright/test'
import { loginAsAdmin } from './testCredentials'

test.describe('Authentication', () => {
  test('should show login page for unauthenticated users', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL('/login')
  })

  test('should login with valid credentials', async ({ page }) => {
    await loginAsAdmin(page)
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: /Compliance Dashboard/i })).toBeVisible()
  })

  test('should show error for invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await page.fill('input[type="email"]', 'wrong@example.com')
    await page.fill('input[type="password"]', 'wrongpass')
    await page.click('button[type="submit"]')
    await expect(page.locator('text=Invalid')).toBeVisible()
  })

  test('should logout user', async ({ page }) => {
    await loginAsAdmin(page)
    await page.waitForURL('/')

    await page.getByRole('button', { name: 'Profile options' }).click()
    await page.getByRole('button', { name: 'Logout' }).click()
    await expect(page).toHaveURL('/login')
  })
})
