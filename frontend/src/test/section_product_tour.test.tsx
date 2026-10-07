import { beforeEach, describe, expect, it } from 'vitest'
import { getProductTour, PRODUCT_OVERVIEW_TOUR } from '../components/productTourCatalog'
import { productTourKey, readProductTour, writeProductTour } from '../components/productTourState'

function profile(url: string) {
  const parsed = new URL(url, 'https://synthetic.example.test')
  return getProductTour(parsed.pathname, parsed.search, parsed.hash)
}

// Independent user-facing routing contract: orientation belongs to a section,
// rather than to one record, filter, or selected tab within that section.
const sections = [
  ['/', 'work'], ['/licence-applications', 'licences'], ['/certification-projects', 'certifications'],
  ['/change-management', 'changes'], ['/requirements', 'requirements'], ['/review-cycles', 'assessments'],
  ['/preparation', 'forms'], ['/library?section=templates', 'templates'], ['/library?section=evidence', 'evidence'],
  ['/answer-review', 'answer-review'], ['/access-teams', 'teams'], ['/program-workspace', 'assurance'],
  ['/reports', 'reports'], ['/account', 'account'], ['/market-setup', 'market-setup'],
  ['/jurisdictions', 'jurisdictions'], ['/admin/settings', 'settings'], ['/admin/users', 'users'],
  ['/admin/feedback', 'feedback'],
] as const

const variants = [
  ['/licence-applications', '/licence-applications?create=1', '/licence-applications?application=one', '/licence-applications?application=two&tab=forms', '/licence-applications?application=two&tab=approval', '/licence-applications?application=two&tab=history', '/licence-applications?application=two#authority-queries'],
  ['/certification-projects', '/certification-projects?project=one', '/certification-projects?project=two&section=requirements', '/certification-projects?project=two&section=testing', '/certification-projects?project=two&section=reports', '/certification-projects?project=two&section=history', '/certification-projects?project=two&section=baseline'],
  ['/requirements', '/requirements/sets/one', '/requirements/sets/two/edit', '/requirements/sets/two/import', '/requirements/requirement-one', '/library?section=requirements'],
  ['/review-cycles', '/review-cycles/one', '/review-cycles/two'],
  ['/change-management', '/change-management?change=one', '/change-management?tab=components', '/change-management?tab=programme', '/change-management?tab=baselines', '/change-management?tab=reports'],
  ['/', '/?view=mine', '/?view=team', '/?view=programmes'],
  ['/account', '/account?section=account', '/account?section=notifications'],
  ['/reports', '/reports?section=reviews&review=one', '/reports?section=changes', '/reports?section=audit'],
  ['/admin/settings', '/admin/settings?section=jira', '/admin/settings?section=email', '/admin/settings?section=ai', '/admin/settings?section=backups'],
] as const

describe('section orientations', () => {
  it.each(sections)('offers concise orientation for %s', (url, id) => {
    const tour = profile(url)
    expect(tour.id).toBe(id)
    expect(tour.title.trim()).not.toBe('')
    expect(tour.summary.trim()).not.toBe('')
    expect(tour.steps.length).toBeGreaterThanOrEqual(4)
    expect(tour.steps.length).toBeLessThanOrEqual(6)
  })

  it.each(variants.map(urls => [urls[0], urls] as const))('keeps orientation stable throughout %s', (base, urls) => {
    const orientation = profile(base)
    for (const url of urls) expect(profile(url)).toEqual(orientation)
  })

  it('chooses form and resource orientations without splitting application packs', () => {
    expect(profile('/licence-applications?application=one&case=form-one').id).toBe('forms')
    expect(profile('/licence-applications?application=one&tab=templates').id).toBe('licences')
    expect(profile('/licence-applications?application=one&tab=evidence').id).toBe('licences')
    expect(profile('/preparation?case=form-two').id).toBe('forms')
    expect(profile('/preparation?tab=templates').id).toBe('templates')
    expect(profile('/preparation?tab=evidence').id).toBe('evidence')
    expect(profile('/library?section=forms').id).toBe('forms')
    expect(profile('/library?section=unknown').id).toBe('templates')
  })

  it('keeps the global introduction separate from section orientation', () => {
    expect(profile('/guide')).toEqual(PRODUCT_OVERVIEW_TOUR)
    expect(PRODUCT_OVERVIEW_TOUR.steps.length).toBe(8)
    expect(profile('/guide').id).not.toBe(profile('/').id)
  })

  it('explains licence and certification purpose without claiming external acceptance', () => {
    const copy = (url: string) => profile(url).steps.map(step => `${step.title} ${step.description}`).join(' ')
    expect(copy('/licence-applications')).toMatch(/internal approval/i)
    expect(copy('/licence-applications')).toMatch(/authority/i)
    expect(copy('/licence-applications')).toMatch(/submission/i)
    expect(copy('/certification-projects')).toMatch(/approved requirements|approved requirement/i)
    expect(copy('/certification-projects')).toMatch(/provider|testing/i)
    expect(copy('/certification-projects')).toMatch(/authority|external/i)
  })

  it('uses authored literal guidance and valid selectors rather than record content or HTML', () => {
    const tours = sections.map(([url]) => profile(url)).concat(PRODUCT_OVERVIEW_TOUR)
    for (const tour of tours) {
      for (const step of tour.steps) {
        expect(step.title.trim().length).toBeGreaterThan(2)
        expect(step.description.trim().length).toBeGreaterThan(35)
        expect(`${step.title} ${step.description}`).not.toMatch(/<\/?(?:script|img|iframe|a|div|button)\b|javascript:|example\.test|pack-one|project-one/i)
        if (step.target) expect(() => document.querySelector(step.target!)).not.toThrow()
      }
    }
  })
})

describe('orientation persistence', () => {
  beforeEach(() => localStorage.clear())

  it('retains a section decision across its records and tabs but isolates other sections and users', () => {
    const licences = profile('/licence-applications')
    const certifications = profile('/certification-projects')
    writeProductTour('synthetic-user', { status: 'completed', step: licences.steps.length - 1 }, licences.id)
    writeProductTour('synthetic-user', { status: 'dismissed', step: 0 }, certifications.id)
    expect(readProductTour('synthetic-user', profile('/licence-applications?application=two&tab=approval')))
      .toEqual({ status: 'completed', step: licences.steps.length - 1 })
    expect(readProductTour('synthetic-user', certifications)).toEqual({ status: 'dismissed', step: 0 })
    expect(readProductTour('other-user', licences)).toBeNull()
    expect(readProductTour('synthetic-user', profile('/reports'))).toBeNull()
    expect(productTourKey('synthetic-user', licences.id)).not.toBe(productTourKey('synthetic-user', certifications.id))
  })

  it('accepts valid progress and rejects an impossible step for the selected orientation', () => {
    const tour = profile('/licence-applications')
    writeProductTour('synthetic-user', { status: 'interrupted', step: tour.steps.length - 1 }, tour.id)
    expect(readProductTour('synthetic-user', tour)?.step).toBe(tour.steps.length - 1)
    localStorage.setItem(productTourKey('synthetic-user', tour.id), JSON.stringify({ status: 'interrupted', step: tour.steps.length }))
    expect(readProductTour('synthetic-user', tour)).toBeNull()
  })

  it('does not let a previous introduction version suppress new section orientation', () => {
    localStorage.setItem('cap:product-tour:v1:synthetic-user', JSON.stringify({ status: 'completed', step: 3 }))
    expect(readProductTour('synthetic-user', profile('/licence-applications'))).toBeNull()
    expect(readProductTour('synthetic-user', PRODUCT_OVERVIEW_TOUR)).toBeNull()
  })
})
