import { useEffect, useRef, useState, type ButtonHTMLAttributes } from 'react'
import Button from './Button'

/** Copies only when explicitly clicked; never changes or saves the source value. */
export default function CopyButton({ value, label = 'Copy', successMessage = 'Copied.', className, title, disabled, ...props }:
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'onClick' | 'value' | 'type'> & {
    value: string
    label?: string
    successMessage?: string
  }) {
  const [status, setStatus] = useState<'idle' | 'copying' | 'copied' | 'error'>('idle')
  const request = useRef(0)
  const busy = useRef(false)
  const resetTimer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    request.current += 1
    busy.current = false
    setStatus('idle')
    clearTimeout(resetTimer.current)
    return () => { request.current += 1; clearTimeout(resetTimer.current) }
  }, [value])

  const copy = async () => {
    if (busy.current || disabled || !value) return
    const currentRequest = ++request.current
    busy.current = true
    clearTimeout(resetTimer.current)
    setStatus('copying')
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(value)
      if (currentRequest !== request.current) return
      setStatus('copied')
      resetTimer.current = setTimeout(() => setStatus('idle'), 2500)
    } catch {
      if (currentRequest === request.current) setStatus('error')
    } finally {
      if (currentRequest === request.current) busy.current = false
    }
  }

  return <span className="ui-copy-control">
    <Button {...props} className={className} size="sm" variant="ghost" onClick={() => { void copy() }}
      disabled={disabled || !value} aria-busy={status === 'copying' || undefined} title={title || label}>
      <svg aria-hidden="true" viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.6">
        <rect x="6.5" y="6.5" width="10" height="10" rx="2" /><path d="M12.5 6.5v-2a2 2 0 0 0-2-2h-6a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
      </svg>
      {status === 'copying' ? 'Copying…' : label}
    </Button>
    <span role={status === 'error' ? 'alert' : 'status'} aria-live={status === 'error' ? 'assertive' : 'polite'}
      className={status === 'error' ? 'text-xs text-danger' : 'text-xs text-muted'}>
      {status === 'copied' ? successMessage : status === 'error' ? 'Could not copy. Select the text and copy it manually.' : ''}
    </span>
  </span>
}
