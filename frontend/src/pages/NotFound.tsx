import { useLocation } from 'react-router-dom'
import LinkButton from '../components/ui/LinkButton'

export default function NotFound() {
  const location = useLocation()
  return <section className="cap-empty-state mx-auto max-w-3xl" aria-labelledby="missing-page-title">
    <svg aria-hidden="true" className="mb-5 h-9 w-9 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2-2V9zM14 3v6h6M9 14h6M9 17h4" /></svg>
    <h1 id="missing-page-title">Page not found</h1>
    <p>The page at <span className="break-all font-medium text-ink">{location.pathname}</span> is unavailable. The link may have changed.</p>
    <div className="mt-6 flex flex-wrap gap-3"><LinkButton to="/" variant="primary">Back to overview</LinkButton><LinkButton to="/guide">Open the guide</LinkButton></div>
  </section>
}
