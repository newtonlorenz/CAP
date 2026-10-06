import axios from 'axios'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function extractString(value: unknown): string | null {
  if (typeof value === 'string') return value
  return null
}

function formatValidationLocation(value: unknown): string | null {
  if (!Array.isArray(value)) return null

  const parts = value
    .filter((part): part is string | number => typeof part === 'string' || typeof part === 'number')
    .map(String)
    .filter((part) => part !== 'body')

  if (parts.length === 0) return null
  return parts.join('.')
}

function extractValidationArrayDetail(value: unknown): string | null {
  if (!Array.isArray(value)) return null

  const messages = value
    .map((entry) => {
      const asString = extractString(entry)
      if (asString) return asString
      if (!isRecord(entry)) return null

      const message = extractString(entry.msg) || extractString(entry.message)
      if (!message) return null

      const location = formatValidationLocation(entry.loc)
      return location ? `${location}: ${message}` : message
    })
    .filter((message): message is string => Boolean(message && message.trim()))

  if (messages.length === 0) return null
  return messages.join('; ')
}

export function getApiErrorDetail(err: unknown): string | null {
  if (!axios.isAxiosError(err)) return null

  const data: unknown = err.response?.data
  if (!data) return null

  // Some backends return plain text.
  const asString = extractString(data)
  if (asString) return asString

  if (!isRecord(data)) return null

  const detail = extractString(data.detail)
  if (detail) return detail

  const validationDetail = extractValidationArrayDetail(data.detail)
  if (validationDetail) return validationDetail

  if (isRecord(data.detail)) {
    const nestedMessage = extractString(data.detail.message)
    if (nestedMessage) return nestedMessage
    const gates = extractValidationArrayDetail(data.detail.gates)
    if (gates) return gates
  }

  const message = extractString(data.message)
  if (message) return message

  return null
}

export function getApiErrorMessage(err: unknown, fallback: string): string {
  const detail = getApiErrorDetail(err)
  if (detail && detail.trim()) return detail

  if (axios.isAxiosError(err)) {
    const status = err.response?.status
    if (status) return `${fallback} (${status})`
  }

  return fallback
}
