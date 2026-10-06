import DOMPurify from 'dompurify'

const TAG_PATTERN = /<\/?[a-z][\s\S]*>/i

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

export const toEditableHtml = (value: string) => {
  if (!value) return ''
  if (TAG_PATTERN.test(value)) return value
  return escapeHtml(value).replace(/\n/g, '<br />')
}

export const sanitizeRichText = (value: string) => {
  if (!value) return ''
  if (typeof document === 'undefined') return escapeHtml(value)
  return DOMPurify.sanitize(value, {
    ALLOWED_TAGS: ['b', 'strong', 'i', 'em', 'u', 'ul', 'ol', 'li', 'p', 'br', 'div'],
    ALLOWED_ATTR: [],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
  })
}

export const normalizeRichText = (value: string) =>
  sanitizeRichText(toEditableHtml(value))

export const stripHtml = (value: string) => {
  if (!value) return ''
  if (typeof document === 'undefined') {
    return value.replace(/<[^>]*>/g, ' ')
  }
  const template = document.createElement('template')
  template.innerHTML = value
  return template.content.textContent || ''
}
