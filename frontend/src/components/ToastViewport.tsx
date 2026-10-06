import { useToast } from '../contexts/ToastContext'
import { cn } from '../utils/cn'

const kindStyles: Record<string, { ring: string; bg: string; text: string }> = {
  success: {
    ring: 'border-success-line/80',
    bg: 'bg-success-soft/85',
    text: 'text-success',
  },
  error: { ring: 'border-danger-line/80', bg: 'bg-danger-soft/85', text: 'text-danger' },
  info: { ring: 'border-line/80', bg: 'bg-canvas/85', text: 'text-ink' },
}

export default function ToastViewport() {
  const toast = useToast()

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[100] w-[min(420px,calc(100vw-2rem))] space-y-2">
      {toast.toasts.map((t) => {
        const style = kindStyles[t.kind] || kindStyles.info
        return (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto overflow-hidden rounded-2xl border bg-surface/92 shadow-[0_24px_58px_-36px_rgba(15,23,42,0.8)] backdrop-blur-sm',
              style.ring
            )}
            role="status"
            aria-live="polite"
          >
            <div className={cn('px-4 py-3', style.bg)}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className={cn('text-sm font-semibold', style.text)}>{t.title}</div>
                  {t.description ? (
                    <div className="mt-0.5 text-xs text-muted">{t.description}</div>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => toast.dismiss(t.id)}
                  className="rounded-md border border-line bg-surface px-2 py-1 text-xs font-medium text-ink hover:bg-subtle"
                  aria-label="Dismiss notification"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
