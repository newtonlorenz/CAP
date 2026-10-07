export default function ProductTourInvitation({ interrupted, title, summary, stepCount, onStart, onDismiss }: {
  interrupted: boolean
  title: string
  summary: string
  stepCount: number
  onStart: () => void
  onDismiss: () => void
}) {
  return <section aria-label="Product tour invitation" className="mb-5 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-line bg-surface p-4">
    <div>
      <h2 className="text-sm font-semibold text-ink">{interrupted ? `Continue tour: ${title}` : `${title} tour`}</h2>
      <p className="mt-1 text-sm text-muted">{interrupted ? `Resume at your last step. This tour has ${stepCount} steps. Replay it from Help.` : `${summary} ${stepCount} steps. You stay on this page.`}</p>
    </div>
    <div className="flex flex-wrap gap-2">
      <button type="button" onClick={onStart} className="rounded-md bg-brand px-3 py-2 text-sm font-semibold text-white hover:bg-brand-hover">{interrupted ? 'Resume product tour' : 'Start product tour'}</button>
      <button type="button" onClick={onDismiss} className="rounded-md border border-line-strong px-3 py-2 text-sm text-muted hover:bg-subtle">Not now</button>
    </div>
  </section>
}
