import { Link } from 'react-router-dom'

type Stage = 'jurisdiction' | 'requirements' | 'approval' | 'review' | 'complete'

export default function GettingStartedGuide({ stage, isOperator, onRetry, error }: {
  stage: Stage; isOperator: boolean; onRetry?: () => void; error?: boolean
}) {
  if (stage === 'complete') return null
  const certificationNext = stage === 'requirements' ? 'Create a certification project now. Add and check requirements before starting an assessment.'
    : stage === 'approval' ? 'Set up the project and its milestones now. Approve the requirement sets before starting an assessment.'
    : 'Create a certification project or start an assessment from its approved baseline.'
  return <section aria-labelledby="getting-started-heading" className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
    <h2 id="getting-started-heading" className="text-lg font-semibold text-ink">Get started</h2>
    {stage === 'jurisdiction' ? <>
      <p className="mt-2 text-sm text-muted">Choose a jurisdiction before starting an application, certification project or change register.</p>
      {isOperator ? <Link to="/jurisdictions" className="mt-3 inline-flex min-h-10 items-center font-medium text-accent hover:underline">Open jurisdictions</Link>
        : <p className="mt-3 text-sm text-ink">Ask your installation operator to run the local setup command.</p>}
    </> : <>
      <p className="mt-2 text-sm text-muted">Choose the work you need to prepare. You can start a licence pack or certification project before approving requirements.</p>
      <ul className="mt-4 divide-y divide-line">
        <li className="py-3"><Link to="/licence-applications?create=1" className="font-semibold text-accent hover:underline">Start a licence pack</Link><p className="mt-1 text-sm text-muted">Prepare the application forms, personal declarations and supporting documents.</p></li>
        <li className="py-3"><Link to="/certification-projects" className="font-semibold text-accent hover:underline">Start a certification</Link><p className="mt-1 text-sm text-muted">{certificationNext}</p><Link to="/requirements" className="mt-2 inline-flex text-sm text-accent hover:underline">Open shared requirements</Link></li>
        <li className="py-3"><Link to="/change-management" className="font-semibold text-accent hover:underline">Start change management</Link><p className="mt-1 text-sm text-muted">Create a component register, record a proposed change and track its decision and supporting assessment.</p></li>
      </ul>
    </>}
    {error && <div role="alert" className="mt-3 text-sm text-danger">Certification setup progress could not be loaded. <button type="button" onClick={onRetry} className="font-semibold underline">Try again</button></div>}
  </section>
}
