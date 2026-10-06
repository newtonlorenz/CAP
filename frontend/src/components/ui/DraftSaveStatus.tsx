import Button from './Button'

export type DraftSaveState = 'saved' | 'dirty' | 'saving' | 'error' | 'conflict'

const labels: Record<DraftSaveState, string> = {
  saved: 'Saved', dirty: 'Unsaved', saving: 'Saving…', error: 'Not saved', conflict: 'Conflict',
}

/** Persistence feedback only; approval and review decisions are separate states. */
export default function DraftSaveStatus({ state, onRetry, message }: {
  state: DraftSaveState
  onRetry?: () => void
  message?: string
}) {
  const failed = state === 'error' || state === 'conflict'
  return <span className="ui-draft-status" data-state={state}>
    <span role={failed ? 'alert' : 'status'} aria-live={failed ? 'assertive' : 'polite'} aria-atomic="true">
      <span className="font-semibold">{labels[state]}</span>{message && <span> · {message}</span>}
    </span>
    {state === 'error' && onRetry && <Button variant="ghost" size="sm" onClick={onRetry}>Retry save</Button>}
  </span>
}
