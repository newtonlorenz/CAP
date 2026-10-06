import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import SubmissionChecklistEditor from '../components/SubmissionChecklistEditor'
import NextBestActionsPanel from '../pages/dashboard/NextBestActionsPanel'
import { buildCsv } from '../utils/csv'
import type { SubmissionChecklist } from '../types'

const checklist: SubmissionChecklist = { sections: [{ id: 'custom', title: 'Operator handover', items: [{ id: 'check', label: 'Evidence reconciled', required: true, completed: false, guidance: 'Match the report to the evidence index.' }] }] }

describe('Section review regressions', () => {
  it('preserves custom checklist items and requires an explicit successful save', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce({})
    render(<SubmissionChecklistEditor checklist={checklist} readOnly={false} saving={false} onSave={save} />)
    const button = screen.getByRole('button', { name: 'Save checklist' })
    expect(button).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(button)
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('checkbox')).toBeChecked()
    expect(button).toBeEnabled()
    fireEvent.click(button)
    await waitFor(() => expect(button).toBeDisabled())
    expect(save.mock.calls[1][0].sections[0].items[0]).toMatchObject({ id: 'check', completed: true, guidance: 'Match the report to the evidence index.' })
  })
  it('prevents changing a checklist under approval or locked', () => {
    render(<SubmissionChecklistEditor checklist={checklist} readOnly saving={false} onSave={vi.fn()} />)
    expect(screen.getByRole('checkbox')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save checklist' })).not.toBeInTheDocument()
  })
  it('distinguishes a failed next-actions request from an empty queue', () => {
    const retry = vi.fn()
    render(<MemoryRouter><NextBestActionsPanel actions={[]} isError onRetry={retry} /></MemoryRouter>)
    expect(screen.queryByText(/No pending/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalledOnce()
  })
  it('quotes multiline CSV and neutralises spreadsheet formulas in user text', () => {
    expect(buildCsv(['Title', 'Value'], [['a,"b"\nc', '=1+1'], ['\t@SUM(A1)', -5], [' +2', null]]))
      .toBe('"Title","Value"\r\n"a,""b""\nc","\'=1+1"\r\n"\'\t@SUM(A1)","-5"\r\n"\' +2",""')
  })
})
