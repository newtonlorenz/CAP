import { afterEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { parseSiteContent } from '../config/siteContent'
import { useSiteContent } from '../contexts/SiteContentContext'
import SiteContentProvider from '../contexts/SiteContentProvider'
import { defaultSiteContent } from '../config/siteContent'
import shipped from '../../public/site-content.json'

function ContentProbe() {
  const { brand, login } = useSiteContent()
  return <><h1>{login.heading}</h1><p>{brand.name}</p></>
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

it('keeps the shipped content file in step with the fallback', () => {
  expect(shipped).toEqual(defaultSiteContent)
})

it('loads deployment text from the application base path', async () => {
  vi.stubEnv('BASE_URL', '/cap/')
  const request = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ brand: { name: 'Internal CAP' }, login: { heading: 'Review records' } }),
  })
  vi.stubGlobal('fetch', request)

  render(<SiteContentProvider><ContentProbe /></SiteContentProvider>)

  expect(await screen.findByRole('heading', { name: 'Review records' })).toBeInTheDocument()
  expect(screen.getByText('Internal CAP')).toBeInTheDocument()
  expect(request).toHaveBeenCalledWith('/cap/site-content.json', expect.objectContaining({
    cache: 'no-store', credentials: 'omit',
  }))
})

it('uses neutral defaults for invalid fields and renders configured text literally', async () => {
  const parsed = parseSiteContent({
    brand: { name: 42 },
    login: { heading: '<script>alert(1)</script>', information: [{ title: 'Reviews' }] },
  })
  expect(parsed.brand.name).toBe('CAP')
  expect(parsed.login.information).toEqual([])

  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => parsed }))
  render(<SiteContentProvider><ContentProbe /></SiteContentProvider>)
  expect(await screen.findByRole('heading', { name: '<script>alert(1)</script>' })).toBeInTheDocument()
  expect(document.querySelector('script')).toBeNull()
})
