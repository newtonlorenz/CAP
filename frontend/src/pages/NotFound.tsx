import { Link, useLocation } from 'react-router-dom'

export default function NotFound() {
  const location = useLocation()

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10">
      <div className="app-surface app-surface-default rounded-2xl p-6">
        <div className="text-sm font-semibold text-muted">404</div>
        <h1 className="mt-2 text-2xl font-semibold text-ink">Page not found</h1>
        <p className="mt-2 text-sm text-muted">
          No route matches <span className="font-mono">{location.pathname}</span>.
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to="/"
            className="inline-flex items-center rounded-lg border border-transparent bg-brand px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-brand-hover"
          >
            Go to Dashboard
          </Link>
          <Link
            to="/requirements"
            className="inline-flex items-center rounded-full border border-line-strong bg-surface/85 px-4 py-2 text-sm font-semibold text-ink hover:border-brand-line hover:text-accent"
          >
            Go to Requirements
          </Link>
        </div>
      </div>
    </div>
  )
}
