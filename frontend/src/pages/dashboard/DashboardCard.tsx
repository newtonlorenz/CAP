import type { ReactNode } from 'react'

type DashboardCardVariant = 'hero' | 'default' | 'subtle'

export default function DashboardCard({
  title,
  actions,
  children,
  variant = 'default',
  className,
}: {
  title: string
  actions?: ReactNode
  children: ReactNode
  variant?: DashboardCardVariant
  className?: string
}) {
  const variantClass =
    variant === 'hero'
      ? 'dashboard-surface-hero'
      : variant === 'subtle'
        ? 'dashboard-surface-subtle'
        : 'dashboard-surface-default'

  return (
    <section
      className={['dashboard-surface min-w-0 rounded-md p-4 sm:p-5', variantClass, className || '']
        .filter(Boolean)
        .join(' ')}
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <h2 className="dashboard-card-heading text-lg font-semibold text-ink">{title}</h2>
        {actions ? <div className="min-w-0 max-w-full">{actions}</div> : null}
      </div>
      {children}
    </section>
  )
}
