import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../utils/cn'

export default function Card({
  children,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return (
    <div
      className={cn('app-surface app-surface-default rounded-md', className)}
      {...props}
    >
      {children}
    </div>
  )
}
