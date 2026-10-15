import type { DocumentationExpectation, ExpectationDraft } from '../../types/documentation'

export const emptyExpectation = (projectId?: string): ExpectationDraft => ({ title: '', description: '', category: '', interpretation: '', basis: '', applicability: 'unknown', not_applicable_reason: '', responsible_party: '', owner_id: null, source_reference: '', project_id: projectId || null })

export function expectationReasons(item: DocumentationExpectation): string[] {
  return [...new Set(item.derived_reasons || [])]
}
