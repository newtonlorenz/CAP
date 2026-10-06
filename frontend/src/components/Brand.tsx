import { useSiteContent } from '../contexts/SiteContentContext'

export default function Brand({ compact = false }: { compact?: boolean }) {
  const { brand } = useSiteContent()
  return <span className="brand-lockup">
    <svg className="brand-mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <path d="M23 9.5h-9a6.5 6.5 0 0 0 0 13h9" stroke="white" strokeWidth="3" strokeLinecap="round" />
      <circle cx="23" cy="9.5" r="2" fill="#E8C77A" />
      <circle cx="23" cy="22.5" r="2" fill="#E8C77A" />
    </svg>
    {!compact && <span><span className="brand-name">{brand.name}</span>{brand.description && <span className="brand-description">{brand.description}</span>}</span>}
  </span>
}
