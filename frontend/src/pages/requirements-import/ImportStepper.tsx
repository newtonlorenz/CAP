type ImportStep = {
  id: 'metadata' | 'qa' | 'approval'
  title: string
  description: string
  complete: boolean
  locked: boolean
}

type ImportStepperProps = {
  steps: ImportStep[]
  currentStepId: ImportStep['id']
  onStepChange: (stepId: ImportStep['id']) => void
}

export default function ImportStepper({ steps, currentStepId, onStepChange }: ImportStepperProps) {
  return (
    <nav aria-label="Import steps" className="mb-4 border-b border-line" data-testid="import-stepper">
      <ol className="grid grid-cols-3 gap-2">
        {steps.map((step, index) => <li key={step.id}>
          <button type="button" disabled={step.locked} aria-current={currentStepId === step.id ? 'step' : undefined}
            aria-describedby={`import-step-${step.id}`} onClick={() => onStepChange(step.id)}
            className={`flex min-h-12 w-full items-center gap-2 border-b-2 py-3 text-left text-sm disabled:text-faint ${currentStepId === step.id ? 'border-accent font-semibold text-accent' : 'border-transparent text-muted hover:text-ink'}`}>
            <span className="tabular-nums" aria-hidden="true">{index + 1}.</span><span>{step.title}</span>
            {step.complete && <svg aria-label="Complete" role="img" className="h-4 w-4 shrink-0 text-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m5 12 4 4 10-10" /></svg>}
          </button>
          <span id={`import-step-${step.id}`} className="sr-only">{step.description}{step.locked ? ' Locked until prior step is complete.' : ''}</span>
        </li>)}
      </ol>
    </nav>
  )
}
