import { PRODUCT_OVERVIEW_TOUR, type ProductTourDefinition } from './productTourCatalog'

// Section tours replace the original four-step introduction.
export const PRODUCT_TOUR_VERSION = 2

export type ProductTourRecord = {
  status: 'dismissed' | 'completed' | 'interrupted'
  step: number
}

export function productTourKey(userId: string, tourId = PRODUCT_OVERVIEW_TOUR.id) {
  return `cap:product-tour:v${PRODUCT_TOUR_VERSION}:${encodeURIComponent(userId)}:${encodeURIComponent(tourId)}`
}

export function readProductTour(userId: string, tour: ProductTourDefinition = PRODUCT_OVERVIEW_TOUR): ProductTourRecord | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(productTourKey(userId, tour.id)) || 'null')
    if (!value || typeof value !== 'object') return null
    const record = value as Partial<ProductTourRecord>
    if (!['dismissed', 'completed', 'interrupted'].includes(record.status || '') ||
      !Number.isInteger(record.step) || record.step! < 0 || record.step! >= tour.steps.length) return null
    return record as ProductTourRecord
  } catch { return null }
}

export function writeProductTour(userId: string, record: ProductTourRecord, tourId = PRODUCT_OVERVIEW_TOUR.id) {
  try { localStorage.setItem(productTourKey(userId, tourId), JSON.stringify(record)) } catch {
    // The controller retains each user's section state when storage is blocked.
  }
}
