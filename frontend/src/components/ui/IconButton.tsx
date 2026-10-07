import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '../../utils/cn'
import Tooltip from './Tooltip'

export default function IconButton({
  children,
  className,
  title,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode }) {
  const button = (
    <button
      type="button"
      className={cn(
        'ui-icon-button inline-flex h-9 w-9 items-center justify-center rounded-md border border-line bg-surface text-muted transition-colors hover:bg-subtle hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50',
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
  return title ? <Tooltip content={title}>{button}</Tooltip> : button
}
