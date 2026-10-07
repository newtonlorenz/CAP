import type { ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import { cn } from '../../utils/cn'
import type { ButtonSize, ButtonVariant } from './Button'

const base =
  'ui-button inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50'

const variants: Record<ButtonVariant, string> = {
  primary: 'border border-transparent bg-brand text-white hover:bg-brand-hover',
  secondary: 'border border-line-strong bg-surface text-ink hover:bg-subtle hover:border-accent',
  ghost: 'border border-transparent text-muted hover:bg-subtle hover:text-ink',
  destructive: 'border border-transparent bg-rose-600 text-white hover:bg-rose-700',
}

const sizes: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
}

export default function LinkButton({
  variant = 'secondary',
  size = 'md',
  className,
  children,
  ...props
}: LinkProps & {
  variant?: ButtonVariant
  size?: ButtonSize
  className?: string
  children: ReactNode
}) {
  return (
    <Link className={cn(base, variants[variant], sizes[size], className)} {...props}>
      {children}
    </Link>
  )
}
