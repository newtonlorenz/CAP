export const PRODUCT_TOUR_VERSION = 1
export const PRODUCT_TOUR_STEP_COUNT = 4

export type ProductTourRecord = {
  status: 'dismissed' | 'completed' | 'interrupted'
  step: number
}

export function productTourKey(userId: string) {
  return `cap:product-tour:v${PRODUCT_TOUR_VERSION}:${encodeURIComponent(userId)}`
}

export function readProductTour(userId: string): ProductTourRecord | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(productTourKey(userId)) || 'null')
    if (!value || typeof value !== 'object') return null
    const record = value as Partial<ProductTourRecord>
    if (!['dismissed', 'completed', 'interrupted'].includes(record.status || '') ||
      !Number.isInteger(record.step) || record.step! < 0 || record.step! >= PRODUCT_TOUR_STEP_COUNT) return null
    return record as ProductTourRecord
  } catch { return null }
}

export function writeProductTour(userId: string, record: ProductTourRecord) {
  try { localStorage.setItem(productTourKey(userId), JSON.stringify(record)) } catch {
    // The controller retains this state for the current session when storage is blocked.
  }
}
