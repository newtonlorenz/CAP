import type { HTMLAttributes, ReactNode, TableHTMLAttributes } from 'react'
import { cn } from '../../utils/cn'

export function Table({
  className,
  ...props
}: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <table
      className={cn('min-w-full divide-y divide-line/80', className)}
      {...props}
    />
  )
}

export function THead({
  className,
  ...props
}: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn('bg-canvas', className)} {...props} />
}

export function TBody({
  className,
  ...props
}: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn('divide-y divide-line/80 bg-surface', className)} {...props} />
}

export function TR({
  className,
  ...props
}: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn('transition-colors hover:bg-brand-soft/40', className)} {...props} />
}

export function TH({
  className,
  ...props
}: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        'px-6 py-3 text-left text-[11px] font-semibold tracking-wide text-muted',
        className
      )}
      {...props}
    />
  )
}

export function TD({
  className,
  ...props
}: HTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('px-6 py-4 text-sm text-ink', className)} {...props} />
}

export function TableEmpty({
  colSpan,
  children,
}: {
  colSpan: number
  children: ReactNode
}) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-6 py-10 text-center text-sm text-muted">
        {children}
      </td>
    </tr>
  )
}
