import { describe, expect, it } from 'vitest'
import type { RequirementSetSummary } from '../types'
import { getRequirementSetRouting } from '../utils/requirementSetRouting'

const makeSet = (overrides: Partial<RequirementSetSummary>): RequirementSetSummary => ({
  document_id: 'set-1',
  jurisdiction_id: 'jur-1',
  filename: 'imported.pdf',
  name: 'Imported Set',
  document_type: 'annex_b',
  version: null,
  testing_frequency: null,
  document_status: 'draft',
  archived_at: null,
  requirements_total: 0,
  requirements_active: 0,
  current_version_id: null,
  current_version_number: null,
  current_version_status: null,
  ...overrides,
})

describe('getRequirementSetRouting', () => {
  it('routes non-manual draft sets with requirements to edit mode for admin/manager', () => {
    const set = makeSet({
      filename: 'source.pdf',
      document_status: 'draft',
      requirements_total: 3,
      requirements_active: 3,
    })

    const result = getRequirementSetRouting(set, true)

    expect(result.openPath).toBe('/requirements/sets/set-1/edit')
    expect(result.openLabel).toBe('Edit')
    expect(result.canEdit).toBe(true)
  })

  it('routes non-manual draft sets with requirements to the view page for non-admin users', () => {
    const set = makeSet({
      filename: 'source.pdf',
      document_status: 'draft',
      requirements_total: 3,
      requirements_active: 3,
    })

    const result = getRequirementSetRouting(set, false)

    expect(result.openPath).toBe('/requirements/sets/set-1')
    expect(result.openLabel).toBe('Open')
    expect(result.canEdit).toBe(false)
  })

  it('routes non-manual draft sets without requirements to import and disallows edit', () => {
    const set = makeSet({
      filename: 'source.pdf',
      document_status: 'draft',
      requirements_total: 0,
      requirements_active: 0,
    })

    const result = getRequirementSetRouting(set, true)

    expect(result.openPath).toBe('/requirements/sets/set-1/import')
    expect(result.openLabel).toBe('Import')
    expect(result.canEdit).toBe(false)
  })

  it('routes non-manual approved sets to the view page and allows edit for admin/manager', () => {
    const set = makeSet({
      filename: 'source.pdf',
      document_status: 'approved',
      requirements_total: 4,
      requirements_active: 4,
    })

    const result = getRequirementSetRouting(set, true)

    expect(result.openPath).toBe('/requirements/sets/set-1')
    expect(result.openLabel).toBe('Open')
    expect(result.canEdit).toBe(true)
  })

  it('routes manual draft sets without requirements to the view page and allows edit for admin/manager', () => {
    const set = makeSet({
      filename: 'manual-placeholder.pdf',
      document_status: 'draft',
      requirements_total: 0,
      requirements_active: 0,
    })

    const result = getRequirementSetRouting(set, true)

    expect(result.openPath).toBe('/requirements/sets/set-1')
    expect(result.openLabel).toBe('Open')
    expect(result.canEdit).toBe(true)
  })

  it('routes source-free manual drafts without requirements to the view page', () => {
    const set = makeSet({ filename: null, name: 'Manual set', document_status: 'draft' })

    const result = getRequirementSetRouting(set, true)

    expect(result.openPath).toBe('/requirements/sets/set-1')
    expect(result.openLabel).toBe('Open')
    expect(result.canEdit).toBe(true)
  })

  it('routes a real uploaded manual.pdf to import when it has no requirements', () => {
    const set = makeSet({ filename: 'manual.pdf', has_source: true, document_status: 'uploaded' })

    const result = getRequirementSetRouting(set, true)

    expect(result.openPath).toBe('/requirements/sets/set-1/import')
    expect(result.openLabel).toBe('Import')
  })

  it('allows edit for non-manual extracted sets before approval', () => {
    const set = makeSet({
      filename: 'source.pdf',
      document_status: 'extracted',
      requirements_total: 0,
      requirements_active: 0,
    })

    const result = getRequirementSetRouting(set, true)

    expect(result.openPath).toBe('/requirements/sets/set-1/import')
    expect(result.openLabel).toBe('Import')
    expect(result.canEdit).toBe(true)
  })
})
