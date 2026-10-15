import type { DocumentationProcess, ProcessTarget } from '../../types/documentation'

export function safeRegisterReturn(value: string | null): string | null {
  return value && /^\/(library|certification-projects|requirements)(?:[/?#]|$)/.test(value) && !value.includes('\\') && !Array.from(value).some(character => character.charCodeAt(0) < 32) ? value : null
}

export function processTargetHref(target: ProcessTarget, returnTo: string): string | null {
  if (!target.available || !target.href || !/^\/(review-cycles|licence-applications|preparation)(?:[/?]|$)/.test(target.href)) return null
  const parsed = new URL(target.href, 'https://cap.invalid')
  parsed.searchParams.set('return_register', returnTo)
  parsed.searchParams.set('evidence', '1')
  if (target.requirement_id) parsed.searchParams.set('register_requirement', target.requirement_id)
  if (target.requirement_set_version_id) parsed.searchParams.set('register_version', target.requirement_set_version_id)
  if (target.kind === 'review_item') parsed.searchParams.set('register_target', '1')
  return `${parsed.pathname}${parsed.search}${parsed.hash}`
}

export function reviewProcessHref(process: DocumentationProcess | null | undefined, returnTo: string): string | null {
  if (!process?.available || process.kind !== 'review' || !process.id || !process.href?.startsWith('/review-cycles/')) return null
  const parsed = new URL(process.href, 'https://cap.invalid')
  if (parsed.origin !== 'https://cap.invalid' || parsed.pathname !== `/review-cycles/${encodeURIComponent(process.id)}`) return null
  parsed.searchParams.set('return_register', returnTo)
  return `${parsed.pathname}${parsed.search}${parsed.hash}`
}

export function registerSourceMatches(params: URLSearchParams, source?: { requirement_id?: string | null; requirement_set_version_id?: string | null } | null): boolean {
  return Boolean(source?.requirement_id && source.requirement_set_version_id
    && source.requirement_id === params.get('register_requirement')
    && source.requirement_set_version_id === params.get('register_version'))
}

export const targetKey = (target: ProcessTarget) => target.kind === 'review_item' ? `review:${target.review_item_id}` : `form:${target.case_id}:${target.field_key}`
