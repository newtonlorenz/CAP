import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

describe('deployment under /cap/', () => {
  it('keeps API, evidence links and unauthorized login handling under the prefix', async () => {
    vi.stubEnv('BASE_URL', '/cap/')
    vi.resetModules()
    const { default: api, shouldRedirectOnUnauthorized } = await import('../api/client')
    const { buildReviewItemEvidencePreviewUrl } = await import('../utils/reviewEvidence')
    expect(api.defaults.baseURL).toBe('/cap/api/v1')
    expect(buildReviewItemEvidencePreviewUrl('cycle', 'item', 'file')).toBe(
      '/cap/api/v1/review-cycles/cycle/items/item/files/file/preview'
    )
    expect(shouldRedirectOnUnauthorized('/requirements', '/cap/login')).toBe(false)
    expect(shouldRedirectOnUnauthorized('/requirements', '/cap/reviews')).toBe(true)
  })
})
