/** Human-readable dates; native date inputs and exported source values stay unchanged. */
const dateFormatter = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFormatter = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
function parse(value: string | number | Date | null | undefined) {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}
export function formatDate(value: string | number | Date | null | undefined) {
  const date = parse(value)
  return date ? dateFormatter.format(date) : '—'
}
export function formatDateTime(value: string | number | Date | null | undefined) {
  const date = parse(value)
  return date ? dateTimeFormatter.format(date) : '—'
}
