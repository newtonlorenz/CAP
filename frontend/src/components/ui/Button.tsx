import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '../../utils/cn'
import Tooltip from './Tooltip'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive'
export type ButtonSize = 'sm' | 'md'

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

export default function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  children,
  className,
  type,
  disabled,
  title,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  children: ReactNode
}) {
  const button = (
    <button
      className={cn(base, variants[variant], sizes[size], className)}
      type={type ?? 'button'}
      {...props}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? <span className="text-xs">Working...</span> : children}
    </button>
  )
  return title ? <Tooltip content={title}>{button}</Tooltip> : button
}
