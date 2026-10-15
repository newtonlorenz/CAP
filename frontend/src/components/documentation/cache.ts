import type { QueryClient } from '@tanstack/react-query'
import type { PaginatedResponse } from '../../types'
import type { DocumentationExpectation, DocumentationRegister } from '../../types/documentation'

const collectionQueries = new Set(['expectations', 'returned-row', 'expectation-detail', 'process-documents', 'process-target-options', 'reconciliation', 'auditor-requests', 'audit-fields'])

/** Form answer writes affect collection projections, not every register lookup. */
export function invalidateDocumentationCollections(cache: QueryClient) {
  return cache.invalidateQueries({ predicate: query => query.queryKey[0] === 'documentation' && collectionQueries.has(String(query.queryKey[1])) })
}

/** Metadata assignment changes one row and its register revision. */
export function invalidateDocumentationRow(cache: QueryClient, row: DocumentationExpectation) {
  return cache.invalidateQueries({ predicate: query => {
    const [root, kind, id] = query.queryKey
    if (root !== 'documentation') return false
    if (kind === 'registers') return Boolean((query.state.data as PaginatedResponse<DocumentationRegister> | undefined)?.items.some(register => register.id === row.register_id))
    if (['expectation-detail', 'process-documents', 'process-target-options', 'row-review-options'].includes(String(kind))) return id === row.id
    if (kind === 'returned-row') return id === row.register_id && query.queryKey[3] === row.id
    return ['expectations', 'sections', 'register-detail', 'audit-expectation-options', 'import-existing', 'reconciliation', 'auditor-requests'].includes(String(kind)) && id === row.register_id
  } })
}
