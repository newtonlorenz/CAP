import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ChangeReadiness from '../components/workflows/ChangeReadiness'
import type { ChangeEntry } from '../types'

const change = (overrides: Partial<ChangeEntry> = {}): ChangeEntry => ({
  id: 'change-1', status: 'draft', components: [],
  readiness: {
    approval: { ready: false, reasons: [{ code: 'missing_evaluation', message: 'Confirm the impact evaluation.' }] },
    implementation: { ready: false, reasons: [{ code: 'preimplementation_certification', message: 'Certification is required before implementation.' }] },
    verification: { ready: false, reasons: [{ code: 'verification_status', message: 'Only implemented changes can be verified.' }] },
    release_ready: false, rule_profile: 'denmark_scp_3.1', certification_status: 'pending',
  }, ...overrides,
} as ChangeEntry)

describe('change readiness presentation', () => {
  it('shows actual current-phase blockers, their action and separate external requirements', () => {
    const open = vi.fn()
    render(<ChangeReadiness change={change()} prerequisiteAction={() => ({ label: 'Open impact evaluation', onClick: open })} />)
    expect(screen.getByText('Not ready for internal approval')).toBeInTheDocument()
    expect(screen.getByText('1 required check outstanding')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Current change readiness' })).getByText('Confirm the impact evaluation.')).toBeInTheDocument()
    expect(screen.getByText('For implementation')).toBeInTheDocument()
    expect(screen.queryByText(/passed checks/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open impact evaluation' }))
    expect(open).toHaveBeenCalledOnce()
  })

  it('does not infer readiness or passed totals when checks are unavailable', () => {
    render(<ChangeReadiness change={change({ readiness: undefined })} />)
    expect(screen.getByText('Readiness unavailable')).toBeInTheDocument()
    expect(screen.queryByText('Ready for internal approval')).not.toBeInTheDocument()
    expect(screen.queryByText(/passed checks/)).not.toBeInTheDocument()
  })

  it('distinguishes unsupported jurisdiction checks from unavailable readiness', () => {
    render(<ChangeReadiness change={change({ readiness: undefined })} readinessExpected={false} />)
    expect(screen.getByText('Review the change proposal')).toBeInTheDocument()
    expect(screen.queryByText('Readiness unavailable')).not.toBeInTheDocument()
    expect(screen.queryByText('Ready for internal approval')).not.toBeInTheDocument()
    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
  })

  it('switches to implementation blockers after approval', () => {
    render(<ChangeReadiness change={change({ status: 'approved' })} />)
    const current = within(screen.getByRole('region', { name: 'Current change readiness' }))
    expect(current.getByText('Not ready for implementation')).toBeInTheDocument()
    expect(current.getByText('Certification is required before implementation.')).toBeInTheDocument()
    expect(current.queryByText('Confirm the impact evaluation.')).not.toBeInTheDocument()
  })

  it('opens the recorded external evidence when the context link is followed', () => {
    render(<><ChangeReadiness change={change()} /><details id="change-external-evidence"><summary>Evidence record</summary><p>Recorded evidence</p></details></>)
    fireEvent.click(screen.getByRole('link', { name: 'View applicability & evidence' }))
    expect(document.getElementById('change-external-evidence')).toHaveAttribute('open')
  })
})
