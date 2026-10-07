import './workflow-pages.css'
import ReportDownloadRow from '../components/ReportDownloadRow'
import { getApiErrorMessage } from '../api/errors'
import axios from 'axios'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import SectionNav from '../components/ui/SectionNav'
import { useQuery } from '@tanstack/react-query'
import api from '../api/client'
import type { PaginatedResponse, ReviewCycle } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import SoAFieldSelector from '../components/SoAFieldSelector'
import { READABLE_SOA_FIELD_KEYS } from '../utils/soaFields'
import ReviewCycleReportOptions from '../components/ReviewCycleReportOptions'

export default function Reports() {
  const [searchParams, setSearchParams] = useSearchParams()
  const reportSection = ['reviews', 'changes', 'audit'].includes(searchParams.get('section') || '') ? searchParams.get('section')! : 'reviews'
  const setReportSection = (value: string) => setSearchParams((current) => { const next = new URLSearchParams(current); next.set('section', value); return next })
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [isDownloading, setIsDownloading] = useState<string | null>(null)
  const [auditDateRange, setAuditDateRange] = useState({ from: '', to: '' })
  const selectedCycleId = searchParams.get('review') || ''
  const setSelectedCycleId = (value: string) => setSearchParams((current) => { const next = new URLSearchParams(current); if (value) next.set('review', value); else next.delete('review'); return next })
  const [soaFields, setSoaFields] = useState<string[]>(READABLE_SOA_FIELD_KEYS)
  const [soaSelectorOpen, setSoaSelectorOpen] = useState(false)
  const [soaFormat, setSoaFormat] = useState<'xlsx' | 'pdf'>('xlsx')
  const [reviewerDisplay, setReviewerDisplay] = useState<'both' | 'names' | 'emails'>(
    'both'
  )
  const [reportOptionsOpen, setReportOptionsOpen] = useState(false)
  const [cmPeriodDays, setCmPeriodDays] = useState<'90' | '180' | '365'>('90')
  const { user } = useAuth()
  const { jurisdictionId, jurisdictionById } = useJurisdiction()
  const canDownloadChangeManagementReports =
    user?.role === 'admin' || user?.role === 'manager' || user?.role === 'approver'

  const { data: reviewCycles, isError: reviewLoadFailed, refetch: reloadReviews } = useQuery({
    queryKey: ['review-cycles', 'reports', jurisdictionId],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1000')
      if (jurisdictionId) params.set('jurisdiction_id', jurisdictionId)
      const response = await api.get<PaginatedResponse<ReviewCycle>>(
        `/review-cycles?${params.toString()}`
      )
      return response.data
    },
    enabled: !!jurisdictionId && canDownloadChangeManagementReports,
  })

  useEffect(() => {
    if (selectedCycleId && reviewCycles && !reviewCycles.items.some((cycle) => cycle.id === selectedCycleId)) {
      setSearchParams((current) => { const next = new URLSearchParams(current); next.delete('review'); return next }, { replace: true })
    }
  }, [reviewCycles, selectedCycleId, setSearchParams])

  const downloadReport = async (endpoint: string, filename: string, params?: URLSearchParams) => {
    setIsDownloading(endpoint)
    setDownloadError(null)
    try {
      const url = params ? `${endpoint}?${params.toString()}` : endpoint
      const response = await api.get(url, { responseType: 'blob' })
      const blob = new Blob([response.data])
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = filename
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.data instanceof Blob) {
        try { err.response.data = JSON.parse(await err.response.data.text()) } catch { /* Keep the generic message for a non-JSON response. */ }
      }
      setDownloadError(getApiErrorMessage(err, 'Unable to download the report. Please try again.'))
    } finally {
      setIsDownloading(null)
    }
  }

  const openSoaSelector = (format: 'xlsx' | 'pdf') => {
    if (!selectedCycleId) return
    setSoaFormat(format)
    setSoaSelectorOpen(true)
  }

  const confirmSoaDownload = () => {
    if (!selectedCycleId) return
    const params = new URLSearchParams()
    params.set('review_cycle_id', selectedCycleId)
    params.set('format', soaFormat)
    if (soaFields.length) {
      params.set('fields', soaFields.join(','))
    }
    const filename =
      soaFormat === 'pdf'
        ? 'statement-of-applicability.pdf'
        : 'statement-of-applicability.xlsx'
    downloadReport('/reports/statement-of-applicability', filename, params)
    setSoaSelectorOpen(false)
  }

  const openReviewCycleReport = () => {
    if (!selectedCycleId) return
    setReportOptionsOpen(true)
  }

  const confirmReviewCycleReport = () => {
    if (!selectedCycleId) return
    const params = new URLSearchParams()
    params.set('review_cycle_id', selectedCycleId)
    params.set('reviewer_display', reviewerDisplay)
    downloadReport('/reports/review-cycle-report', 'review-cycle-report.pdf', params)
    setReportOptionsOpen(false)
  }

  if (user && !canDownloadChangeManagementReports) return <div className="space-y-4"><h1 className="text-2xl font-semibold">Reports</h1><div className="rounded-xl border border-line bg-surface p-5"><p className="text-sm text-muted">Report exports are available to managers, approvers and administrators. You can continue your assigned evidence and assessment work.</p><Link to="/review-cycles" className="mt-4 inline-block text-sm font-semibold text-accent underline">Open assessments</Link></div></div>

  return (
    <div className="workflow-page reports-page min-w-0">
      {downloadError && <p role="alert" className="rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger">{downloadError}</p>}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink">Reports</h1><p className="mt-2 text-sm text-muted">Export assessment evidence, controlled-change records and audit history.</p>
        {jurisdictionId && jurisdictionById[jurisdictionId] && (
          <div className="mt-1 text-sm text-muted">
            Jurisdiction: {jurisdictionById[jurisdictionId].name}
          </div>
        )}
      </div>

      <section aria-labelledby="report-choice-heading" className="report-intro mb-6 max-w-3xl">
        <h2 id="report-choice-heading" className="text-lg font-semibold text-ink">Which report do I need?</h2>
        <p className="mt-2 text-sm text-muted">Use assessment reports to review compliance and evidence. Use change management reports for component records and verified changes.</p>
        <p className="mt-2 text-sm text-muted">Use Audit trail to investigate who changed a record and when.</p>
      </section>
      {isDownloading && <p role="status" className="text-sm text-muted">Preparing your report…</p>}
      <SectionNav label="Report categories" value={reportSection} onChange={setReportSection} items={[{ id: 'reviews', label: 'Assessment reports' }, { id: 'changes', label: 'Change management' }, { id: 'audit', label: 'Audit trail' }]} />
      <div className="mt-5 space-y-6">
        <section hidden={reportSection !== 'audit'} aria-label="Audit trail reports">            <div className="app-surface app-surface-default rounded-2xl p-6">
              <h3 className="text-lg font-semibold text-ink">Audit Trail</h3>
              <p className="mt-2 mb-4 text-sm text-muted">
                CSV export of system activity across all jurisdictions you can access. Dates include the entire selected day in UTC.
              </p>
              <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm text-muted">From</label>
                  <input
                    aria-label="Audit from date"
                    type="date"
                    max={auditDateRange.to || undefined}
                    value={auditDateRange.from}
                    onChange={(e) =>
                      setAuditDateRange({ ...auditDateRange, from: e.target.value })
                    }
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm text-muted">To</label>
                  <input
                    aria-label="Audit to date"
                    type="date"
                    min={auditDateRange.from || undefined}
                    value={auditDateRange.to}
                    onChange={(e) =>
                      setAuditDateRange({ ...auditDateRange, to: e.target.value })
                    }
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2"
                  />
                </div>
              </div>
              <button
                onClick={() => {
                  const params = new URLSearchParams()
                  if (auditDateRange.from) params.append('from_date', auditDateRange.from)
                  if (auditDateRange.to) params.append('to_date', auditDateRange.to)
                  downloadReport('/reports/audit-trail', 'audit-trail.csv', params)
                }}
                disabled={isDownloading !== null || !!(auditDateRange.from && auditDateRange.to && auditDateRange.from > auditDateRange.to)}
                className="rounded-lg border border-transparent bg-brand px-4 py-2 text-white transition-all hover:bg-brand-hover disabled:opacity-50"
              >
                {isDownloading === '/reports/audit-trail' ? 'Downloading...' : 'Download'}
              </button>
            </div></section>
        <section hidden={reportSection !== 'changes'} aria-label="Change management reports">
          <div className="rounded-xl border border-line bg-surface p-4">
            {!canDownloadChangeManagementReports && <p className="text-sm text-muted">Change management report exports are available for manager, approver, and admin roles.</p>}
            {canDownloadChangeManagementReports && (<>
              <div className="divide-y divide-line">
                {[{id: 'components', title: 'Components', description: 'Component inventory and classification.'}, {id: 'hardware-locations', title: 'Hardware Locations', description: 'Registered hardware and hosting locations.'}].map(report => <ReportDownloadRow key={report.id} title={report.title} description={report.description} formats={['csv']} disabled={!jurisdictionId || isDownloading !== null} onDownload={() => {
                  if (!jurisdictionId) return
                  downloadReport(`/reports/change-management/${report.id}`, `change-management-${report.id}.csv`, new URLSearchParams({ jurisdiction_id: jurisdictionId }))
                }} />)}
              </div>
              <div className="mt-3 border-t border-line pt-4">
                <label className="flex flex-wrap items-center gap-3 text-sm font-medium">Reporting period
                  <select aria-label="Period" value={cmPeriodDays} onChange={e => setCmPeriodDays(e.target.value as '90' | '180' | '365')} className="px-3 py-2">
                    <option value="90">90 days</option><option value="180">180 days</option><option value="365">365 days</option>
                  </select>
                </label>
                <div className="divide-y divide-line">
                  {[{id: 'verified-changes', title: 'Verified Changes', description: 'Changes verified during the selected period.'}, {id: 'integration-changes', title: 'Integration Changes', description: 'Integration changes during the selected period.'}].map(report => <ReportDownloadRow key={report.id} title={report.title} description={report.description} formats={['csv']} disabled={!jurisdictionId || isDownloading !== null} onDownload={() => {
                    if (!jurisdictionId) return
                    downloadReport(`/reports/change-management/${report.id}`, `change-management-${report.id}.csv`, new URLSearchParams({ jurisdiction_id: jurisdictionId, period_days: cmPeriodDays }))
                  }} />)}
                </div>
              </div>
                <div className="border-t border-line pt-4">
                  <h3 className="font-semibold">Component history</h3>
                  <p className="my-2 text-sm text-muted">Choose a component by name in its register to export its change history.</p>
                  <Link className="inline-flex rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold text-accent" to="/change-management?tab=reports">Choose a component</Link>
                </div>
              </>
            )}
          </div>
        </section>

        <section hidden={reportSection !== 'reviews'} aria-label="Assessment reports">
          <p className="mb-4 text-sm text-muted">These reports show certification assessment work. Choose an assessment below. Active assessments export the current record; completed assessments export the frozen record. Check external submission requirements with the receiving authority or certification body.</p>
          {selectedCycleId && reviewCycles?.items.find((item) => item.id === selectedCycleId)?.closed_at && <div className="mb-5 rounded-xl border border-brand-line bg-brand-soft p-4">
            <h2 className="font-semibold text-ink">Completed assessment evidence package</h2>
            <p className="my-2 text-sm text-muted">Download the frozen assessment, applicability workbook, gap analysis, source PDFs and evidence files together with a checksum manifest.</p>
            <button type="button" disabled={isDownloading !== null} onClick={() => downloadReport('/reports/review-package', 'completed-review-evidence.zip', new URLSearchParams({ review_cycle_id: selectedCycleId }))} className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{isDownloading === '/reports/review-package' ? 'Preparing package…' : 'Download evidence package (ZIP)'}</button>
          </div>}

          <div className="app-surface app-surface-default space-y-4 rounded-2xl p-6">
            <div>
              {reviewLoadFailed && <p role="alert" className="mb-3 text-sm text-danger">Unable to load assessments. <button type="button" className="underline" onClick={() => reloadReviews()}>Try again</button></p>}
              {reviewCycles?.items.length === 0 && !reviewLoadFailed && <p className="mb-3 text-sm text-muted">No assessments in this jurisdiction yet. <Link to="/review-cycles" className="text-accent underline">Create an assessment</Link> to prepare assessment reports.</p>}
              <label className="mb-1 block text-sm text-muted">Requirement assessment</label>
              <select
                aria-label="Requirement assessment"
                value={selectedCycleId}
                onChange={(e) => setSelectedCycleId(e.target.value)}
                className="w-full max-w-md rounded-xl border border-line-strong bg-surface/90 px-3 py-2"
              >
                <option value="">Select an assessment</option>
                {reviewCycles?.items.map((cycle) => (
                  <option key={cycle.id} value={cycle.id}>
                    {cycle.name}
                  </option>
                ))}
              </select>
              {selectedCycleId && (
                <div className="mt-2 text-sm text-muted">
                  Jurisdiction:{' '}
                  {(() => {
                    const cycle = reviewCycles?.items.find((item) => item.id === selectedCycleId)
                    if (!cycle) return selectedCycleId
                    return (
                      jurisdictionById[cycle.jurisdiction_id]?.name || cycle.jurisdiction_id
                    )
                  })()}
                </div>
              )}
            </div>

            <div className="divide-y divide-line">
              <ReportDownloadRow title="Compliance Summary" description="For managers: a concise overview of status and totals in the selected assessment." formats={['pdf']} disabled={!selectedCycleId || isDownloading !== null} onDownload={() => downloadReport('/reports/compliance-summary', 'compliance-summary.pdf', new URLSearchParams({ review_cycle_id: selectedCycleId }))} />
              <ReportDownloadRow title="Detailed Compliance" description="For compliance teams: mandatory and recommended requirements with their recorded status in the selected assessment." formats={['pdf']} disabled={!selectedCycleId || isDownloading !== null} onDownload={() => downloadReport('/reports/detailed', 'detailed-compliance-report.pdf', new URLSearchParams({ review_cycle_id: selectedCycleId }))} />
              <ReportDownloadRow title="Gap Analysis" description="For owners and reviewers: outstanding controls and evidence gaps to resolve in the selected assessment." formats={['xlsx', 'pdf', 'csv']} disabled={!selectedCycleId || isDownloading !== null} onDownload={format => downloadReport('/reports/gap-analysis', `gap-analysis.${format}`, new URLSearchParams({ review_cycle_id: selectedCycleId, format }))} />
              <ReportDownloadRow title="Statement of Applicability" description="For submission preparation: applicability and evidence from the selected assessment. Choose the fields your receiving authority needs." formats={['xlsx', 'pdf']} disabled={!selectedCycleId || isDownloading !== null} onDownload={format => openSoaSelector(format as 'xlsx' | 'pdf')} />
              <ReportDownloadRow title="Assessment Report" description="For reviewers and auditors: decisions and supporting evidence from the selected assessment." formats={['pdf']} disabled={!selectedCycleId || isDownloading !== null} onDownload={openReviewCycleReport} />
            </div>
          </div>
        </section>
      </div>

      <SoAFieldSelector
        open={soaSelectorOpen}
        selected={soaFields}
        onChange={setSoaFields}
        onClose={() => setSoaSelectorOpen(false)}
        onConfirm={confirmSoaDownload}
      />
      <ReviewCycleReportOptions
        open={reportOptionsOpen}
        value={reviewerDisplay}
        onChange={setReviewerDisplay}
        onClose={() => setReportOptionsOpen(false)}
        onConfirm={confirmReviewCycleReport}
      />
    </div>
  )
}
