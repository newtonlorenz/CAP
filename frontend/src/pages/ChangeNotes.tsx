import './workflow-pages.css'
import Badge from '../components/ui/Badge'
import { releaseNotes } from '../content/releaseNotes'

const dateFormatter = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
})

export default function ChangeNotes() {
  return (
    <div className="workflow-page release-page mx-auto w-full max-w-4xl">
      <header>
        <h1 className="text-2xl font-semibold text-ink">Change notes</h1>
        <p className="mt-2 text-sm text-muted">Feature changes in each app version, newest first.</p>
      </header>

      <div className="mt-7 space-y-4">
        {releaseNotes.map((release, index) => (
          <details key={release.version} open={index === 0} className="group overflow-hidden rounded-xl border border-line bg-surface">
            <summary className="flex cursor-pointer list-none items-start gap-4 p-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-[-2px] sm:p-6 [&::-webkit-details-marker]:hidden">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-lg font-semibold text-ink">Version {release.version}</h2>
                  {index === 0 && <Badge tone="teal">Current version</Badge>}
                </div>
                <p className="mt-1 text-sm text-ink">{release.title}</p>
                <time dateTime={release.date} className="mt-2 block text-xs text-muted">
                  {dateFormatter.format(new Date(`${release.date}T00:00:00Z`))}
                </time>
              </div>
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className="mt-1 h-5 w-5 shrink-0 text-muted group-open:rotate-90">
                <path d="m9 5 7 7-7 7" />
              </svg>
            </summary>
            <div className="border-t border-line p-5 sm:p-6">
              <p className="text-sm leading-relaxed text-muted">{release.summary}</p>
              <ul className="mt-6 space-y-5">
                {release.features.map(feature => (
                  <li key={feature.title}>
                    <h3 className="text-sm font-semibold text-ink">{feature.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted">{feature.description}</p>
                  </li>
                ))}
              </ul>
            </div>
          </details>
        ))}
      </div>
    </div>
  )
}
