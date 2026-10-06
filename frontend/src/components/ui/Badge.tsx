import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../utils/cn'

export type BadgeTone = 'slate' | 'green' | 'amber' | 'red' | 'blue' | 'purple' | 'teal'

const tones: Record<BadgeTone, string> = {
  slate: 'bg-subtle/90 text-ink',
  green: 'bg-success-soft/90 text-success',
  amber: 'bg-warning-soft/90 text-warning',
  red: 'bg-danger-soft/90 text-danger',
  blue: 'bg-info-soft/90 text-info',
  purple: 'bg-brand-soft/90 text-accent',
  teal: 'bg-brand-soft/90 text-accent',
}

export default function Badge({
  children,
  tone = 'slate',
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { children: ReactNode; tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide',
        tones[tone],
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
}
