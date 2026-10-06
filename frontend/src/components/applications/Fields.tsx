import { Children, cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from 'react'
import type { UserMention } from '../../types'
export const inputClass = 'mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink'
export function Field({ label, children }: { label: string; children: ReactNode }) {
  const id = useId()
  return <div className="min-w-0 text-sm font-medium"><label htmlFor={id}>{label}</label>{Children.map(children, child => isValidElement(child) && typeof child.type === 'string' && ['input', 'select', 'textarea'].includes(child.type) ? cloneElement(child as ReactElement<{ id?: string }>, { id }) : child)}</div>
}
export function OwnerField({ users, value, onChange }: { users: UserMention[]; value: string; onChange: (id: string) => void }) {
  return <Field label="Owner"><select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}><option value="">Unassigned</option>{value && !users.some((user) => user.id === value) && <option value={value}>Assigned owner (unavailable)</option>}{users.map((user) => <option key={user.id} value={user.id}>{user.full_name}</option>)}</select></Field>
}
