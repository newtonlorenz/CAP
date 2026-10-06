import { getApiErrorMessage } from '../api/errors'
import type { ToastApi } from '../contexts/ToastContext'

export function notifyApiError(
  toast: ToastApi,
  error: unknown,
  fallbackMessage: string
): void {
  toast.error(getApiErrorMessage(error, fallbackMessage))
}

