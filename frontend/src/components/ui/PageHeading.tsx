import type { ReactNode } from 'react'

/** Shared route heading; actions stay alongside the title and wrap on narrow screens. */
export default function PageHeading({ title, description, actions, children }: {
  title: string
  description?: ReactNode
  actions?: ReactNode
  children?: ReactNode
}) {
  return <header className="cap-page-heading">
    <div className="min-w-0"><h1>{title}</h1>{description && <p className="cap-page-description">{description}</p>}{children}</div>
    {actions && <div className="cap-page-heading-actions">{actions}</div>}
  </header>
}
