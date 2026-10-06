import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import QuestionImport from '../components/preparation/QuestionImport'
import { preparationApi } from '../api/preparation'

vi.mock('../api/preparation', () => ({ preparationApi: { importPreview: vi.fn(), importCapabilities: vi.fn(), enhanceImport: vi.fn(), download: vi.fn() } }))
beforeEach(() => { vi.resetAllMocks(); vi.mocked(preparationApi.importCapabilities).mockResolvedValue({}) })

it('maps workbook columns into ordered questions while excluding confidential answers', async () => {
  const longQuestion = 'Describe the company and its proposed activities.\n' + 'Source wording retained. '.repeat(20)
  vi.mocked(preparationApi.importPreview).mockResolvedValue({ sheets: ['Questions'], sheet_name: 'Questions', warnings: [], rows: [
    ['Number', 'Section', 'Question', 'Type', 'Required', 'Choices', 'Answers'],
    ['1.1', 'Applicant', longQuestion, 'multiline', 'yes', '', 'CONFIDENTIAL company details'],
    ['1.2', '', 'Is the applicant registered?', 'checkbox', 'yes', '', 'true'],
    ['2.1', 'Operations', 'Licence category', 'choice', 'optional', 'Casino|Betting', 'Casino'],
  ] })
  const imported = vi.fn()
  render(<QuestionImport existing={[]} onImport={imported} />)
  fireEvent.click(screen.getByText('Import questions from Excel'))
  fireEvent.change(screen.getByLabelText('Question spreadsheet'), { target: { files: [new File(['fixture'], 'questions.xlsx')] } })
  await screen.findByText('Preview · 3 questions')
  expect(screen.queryByText(/CONFIDENTIAL company/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Add 3 questions to form' }))
  expect(imported).toHaveBeenCalledWith([
    expect.objectContaining({ label: `1.1 ${longQuestion.trim()}`, section: 'Applicant', type: 'multiline', required: true }),
    expect.objectContaining({ label: '1.2 Is the applicant registered?', section: 'Applicant', type: 'yes_no' }),
    expect.objectContaining({ label: '2.1 Licence category', section: 'Operations', type: 'choice', required: false, options: ['Casino', 'Betting'] }),
  ])
  expect(JSON.stringify(imported.mock.calls)).not.toContain('CONFIDENTIAL')
})

it('requires correcting unknown types and supports clearing a failed import draft', async () => {
  vi.mocked(preparationApi.importPreview).mockResolvedValue({ sheets: ['Data'], sheet_name: 'Data', warnings: [], rows: [['Question', 'Type'], ['Shareholders', 'repeating table']] })
  const dirty = vi.fn(), imported = vi.fn()
  render(<QuestionImport existing={[]} onImport={imported} onDirtyChange={dirty} />)
  fireEvent.click(screen.getByText('Import questions from Excel'))
  fireEvent.change(screen.getByLabelText('Question spreadsheet'), { target: { files: [new File(['fixture'], 'questions.csv')] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('unknown answer type “repeating table”')
  expect(screen.getByRole('button', { name: 'Add 1 questions to form' })).toBeDisabled()
  expect(imported).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Answer type column'), { target: { value: '-1' } })
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: 'Add 1 questions to form' })).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Clear import' }))
  expect(dirty).toHaveBeenLastCalledWith(false)
  expect(screen.queryByText('Preview · 1 questions')).not.toBeInTheDocument()
})


it('enhances only missing metadata and excludes answers from the external request', async () => {
  vi.mocked(preparationApi.importCapabilities).mockResolvedValue({ jev: { enabled: true, revision: 3, model: 'jev-1.13.0' } })
  vi.mocked(preparationApi.importPreview).mockResolvedValue({ sheets: ['Data'], sheet_name: 'Data', warnings: [], rows: [['Question', 'Type', 'Required', 'Answers'], ['Date of registration', '', '', 'PRIVATE'], ['Company name', 'text', 'yes', 'SECRET']] })
  vi.mocked(preparationApi.enhanceImport).mockResolvedValue({ status: 'completed', suggested_mapping: {}, field_suggestions: [{ row_index: 1, type: 'date', required: false, confidence: .99 }, { row_index: 2, type: 'multiline', required: false, confidence: .99 }], warnings: [], usage: {}, model: 'jev-1.13.0', input_fingerprint: 'fixture' })
  const imported = vi.fn()
  render(<QuestionImport existing={[]} onImport={imported} />)
  fireEvent.click(screen.getByText('Import questions from Excel'))
  fireEvent.change(screen.getByLabelText('Question spreadsheet'), { target: { files: [new File(['fixture'], 'questions.csv')] } })
  await screen.findByText('Preview · 2 questions')
  fireEvent.click(screen.getByRole('checkbox', { name: /I agree to send/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Enhance preview' }))
  await screen.findByText(/Preview checked with Jev/)
  const body = vi.mocked(preparationApi.enhanceImport).mock.calls[0][0]
  expect(JSON.stringify(body)).not.toMatch(/PRIVATE|SECRET/)
  expect(body.settings_revision).toBe(3)
  fireEvent.click(screen.getByRole('button', { name: 'Add 2 questions to form' }))
  expect(imported.mock.calls[0][0]).toEqual([expect.objectContaining({ type: 'date', required: false }), expect.objectContaining({ type: 'text', required: true })])
})

it('discards enhancement results after manual column changes', async () => {
  vi.mocked(preparationApi.importCapabilities).mockResolvedValue({ jev: { enabled: true, revision: 1, model: 'jev-1.13.0' } })
  vi.mocked(preparationApi.importPreview).mockResolvedValue({ sheets: ['Data'], sheet_name: 'Data', warnings: [], rows: [['Question', 'Other'], ['Name', 'Other question']] })
  let finish!: (value: Awaited<ReturnType<typeof preparationApi.enhanceImport>>) => void
  vi.mocked(preparationApi.enhanceImport).mockReturnValue(new Promise((resolve) => { finish = resolve }))
  const imported = vi.fn()
  render(<QuestionImport existing={[]} onImport={imported} />)
  fireEvent.click(screen.getByText('Import questions from Excel'))
  fireEvent.change(screen.getByLabelText('Question spreadsheet'), { target: { files: [new File(['fixture'], 'questions.csv')] } })
  await screen.findByText('Preview · 1 questions')
  fireEvent.click(screen.getByRole('checkbox', { name: /I agree to send/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Enhance preview' }))
  fireEvent.change(screen.getByLabelText('Question text column (required)'), { target: { value: '1' } })
  finish({ status: 'completed', suggested_mapping: {}, field_suggestions: [{ row_index: 1, type: 'date', confidence: 1 }], warnings: [], usage: {}, model: 'jev', input_fingerprint: 'old' })
  await waitFor(() => expect(screen.getByText('Other question')).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Add 1 questions to form' }))
  expect(imported.mock.calls[0][0][0]).toEqual(expect.objectContaining({ label: 'Other question', type: 'text' }))
})

it('offers a downloadable workbook and lets a failed download be retried without creating a draft', async () => {
  const dirty = vi.fn()
  vi.mocked(preparationApi.download).mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce(undefined)
  render(<QuestionImport existing={[]} onImport={vi.fn()} onDirtyChange={dirty} initialOpen />)
  fireEvent.click(screen.getByRole('button', { name: 'Download Excel template' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not download the Excel template. Try again.')
  fireEvent.click(screen.getByRole('button', { name: 'Download Excel template' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(preparationApi.download).toHaveBeenLastCalledWith('templates/import-template', 'CAP-question-import-template.xlsx')
  expect(dirty).not.toHaveBeenCalled()
})
