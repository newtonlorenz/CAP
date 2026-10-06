import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosResponse } from 'axios'
import api from '../api/client'
import RequirementDetail from '../pages/RequirementDetail'
import RequirementsSetEdit from '../pages/RequirementsSetEdit'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'admin', role: 'admin' } }) }))
vi.mock('../contexts/ToastContext', () => ({ useToast: () => ({ error: vi.fn(), success: vi.fn() }) }))
vi.mock('../contexts/JurisdictionContext', () => ({ useJurisdiction: () => ({ jurisdictionId: 'dk', jurisdictionById: { dk: { name: 'Denmark' } }, setJurisdictionId: vi.fn() }) }))
const response = (data: unknown) => ({ data }) as AxiosResponse
const requirements = () => Array.from({ length: 30 }, (_, index) => ({ id: `r${index + 1}`, document_id: 'd1', jurisdiction_id: 'dk', reference_id: String(index + 1), title: `Control ${index + 1}`, text: '<p>Original text</p>', requirement_type: 'mandatory', parent_id: null, sort_order: index, version: 1, active: true }))

function mount(editor = false, query = '') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[editor ? '/requirements/sets/d1/edit' + query : '/requirements/r1']}><Routes><Route path="/requirements/:id" element={<RequirementDetail />} /><Route path="/requirements/sets/:documentId/edit" element={<RequirementsSetEdit />} /></Routes></MemoryRouter></QueryClientProvider>)
}

describe('Source editing reliability', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); vi.mocked(api.post).mockResolvedValue(response({})) })
  function stubReads(items = requirements(), document = { id: 'd1', jurisdiction_id: 'dk', name: 'Certification controls', status: 'draft', document_type: 'annex_b' }) {
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (url === '/documents/d1') return response({ ...document })
      if (url.startsWith('/requirements/sets?')) return response({ items: [{ document_id: 'd1', requirements_total: items.length, requirements_active: items.length }], total: 1 })
      if (url.startsWith('/requirements?')) return response({ items: items.map((item) => ({ ...item })), total: items.length })
      if (url === '/requirements/r1') return response({ ...items[0] })
      return response({ items: [], total: 0 })
    })
    return items
  }

  for (const editor of [false, true]) {
    it(`keeps and autosaves a newer focused edit while an older ${editor ? 'set' : 'detail'} save finishes`, async () => {
      const items = stubReads()
      const pending: Array<() => void> = []
      vi.mocked(api.put).mockImplementation((_url, data) => new Promise((resolve) => pending.push(() => { Object.assign(items[0], data); resolve(response({ ...items[0] })) })))
      mount(editor)
      const title = await screen.findByRole('textbox', { name: editor ? 'Title for 1' : 'Title' })
      fireEvent.change(title, { target: { value: 'First revision' } }); fireEvent.blur(title)
      await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
      fireEvent.change(title, { target: { value: 'Second revision' } })
      await act(async () => pending.shift()!())
      await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
      expect(screen.getByRole('textbox', { name: editor ? 'Title for 1' : 'Title' })).toHaveValue('Second revision')
      expect(vi.mocked(api.put).mock.calls[1][1]).toMatchObject({ title: 'Second revision' })
      await act(async () => pending.shift()!())
      await waitFor(() => expect(screen.queryByText('Saving…')).not.toBeInTheDocument())
      expect(items[0].title).toBe('Second revision')
    })
  }

  it('opens a deep-linked item without rendering thirty editors, and moves through the hierarchy', async () => {
    stubReads(); mount(true, '?item=r26')
    expect(await screen.findByRole('textbox', { name: 'Title for 26' })).toHaveValue('Control 26')
    expect(screen.getAllByRole('textbox', { name: /Title for/ })).toHaveLength(1)
    expect(screen.getByText('26 of 30')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('textbox', { name: 'Title for 27' })).toHaveValue('Control 27')
    fireEvent.click(screen.getByRole('button', { name: 'All requirements' }))
    expect(screen.getAllByRole('textbox', { name: /Title for/ })).toHaveLength(30)
  })


  it('limits the all-requirements editors by depth while keeping a focused descendant editable', async () => {
    const items = requirements().slice(0, 3)
    items[1] = { ...items[1], reference_id: '1.1', parent_id: 'r1' } as unknown as typeof items[0]
    items[2] = { ...items[2], reference_id: '1.1.1', parent_id: 'r2' } as unknown as typeof items[0]
    stubReads(items); mount(true, '?mode=all')
    await screen.findByRole('textbox', { name: 'Title for 1.1.1' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Show levels' }), { target: { value: '1' } })
    expect(screen.getAllByRole('textbox', { name: /Title for/ })).toHaveLength(1)
    fireEvent.change(screen.getByRole('combobox', { name: 'Show levels' }), { target: { value: '2' } })
    expect(screen.getAllByRole('textbox', { name: /Title for/ })).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Focused editing' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('textbox', { name: 'Title for 1.1.1' })).toBeInTheDocument()
    expect(api.put).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'All requirements' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Show levels' }), { target: { value: '1' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Requirements search' }), { target: { value: 'Control 3' } })
    expect(screen.queryByRole('textbox', { name: /Title for/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all levels' }))
    expect(screen.getByRole('textbox', { name: 'Title for 1.1.1' })).toBeInTheDocument()
  })
  it('keeps the depth preset and inferred parent context while type and search filters change', async () => {
    const items = requirements().slice(0, 3)
    items[1] = { ...items[1], reference_id: '1.1', requirement_type: 'recommended' }
    items[2] = { ...items[2], reference_id: '1.1.1', title: 'Unique leaf' }
    stubReads(items); mount(true, '?mode=all')
    await screen.findByRole('textbox', { name: 'Title for 1.1.1' })
    const levels = screen.getByRole('combobox', { name: 'Show levels' })
    expect(within(screen.getByRole('region', { name: 'Requirements outline' })).getByRole('combobox', { name: 'Show levels' })).toBe(levels)
    fireEvent.change(levels, { target: { value: '2' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Requirements search' }), { target: { value: 'Unique leaf' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'Requirement type filter' }), { target: { value: 'mandatory' } })
    expect(levels).toHaveValue('2')
    expect(screen.queryByRole('textbox', { name: /Title for/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1 Control 1' })).toBeDisabled()
    fireEvent.change(levels, { target: { value: '3' } })
    expect(screen.getByRole('textbox', { name: 'Title for 1.1.1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1.1 Control 2' })).toBeDisabled()
    fireEvent.change(screen.getByRole('combobox', { name: 'Requirement type filter' }), { target: { value: 'recommended' } })
    expect(levels).toHaveValue('3')
    expect(screen.getByText('No outline items.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Requirements search' }), { target: { value: '' } })
    expect(levels).toHaveValue('3')
    expect(screen.getAllByRole('textbox', { name: /Title for/ })).toHaveLength(1)
    expect(screen.getByRole('textbox', { name: 'Title for 1.1' })).toBeInTheDocument()
    expect(api.put).not.toHaveBeenCalled()
  })

  it('keeps full parent context when a search only matches a child', async () => {
    const items = requirements()
    items[1] = { ...items[1], reference_id: '1.1', title: 'Unique child', parent_id: 'r1' } as unknown as typeof items[0]
    stubReads(items); mount(true)
    const search = await screen.findByRole('textbox', { name: 'Requirements search' })
    await screen.findByRole('textbox', { name: 'Title for 1' })
    fireEvent.change(search, { target: { value: 'Unique child' } })
    expect(screen.getByRole('textbox', { name: 'Title for 1.1' })).toHaveValue('Unique child')
    expect(screen.queryByText(/Hierarchy mismatch/)).not.toBeInTheDocument()
    expect(screen.getByText('1 of 1')).toBeInTheDocument()
  })

  for (const editor of [false, true]) {
    it(`autosaves a ${editor ? 'set' : 'detail'} draft without blur and never submits or approves it`, async () => {
      const items = stubReads()
      vi.mocked(api.put).mockImplementation(async (_url, data) => { Object.assign(items[0], data); return response(items[0]) })
      mount(editor)
      const title = await screen.findByRole('textbox', { name: editor ? 'Title for 1' : 'Title' })
      fireEvent.change(title, { target: { value: 'Focused draft' } })
      expect(screen.getByText('Unsaved')).toBeInTheDocument()
      await waitFor(() => expect(items[0].title).toBe('Focused draft'), { timeout: 2000 })
      expect(vi.mocked(api.post).mock.calls.some(([url]) => /\/(submit|approve)$/.test(url))).toBe(false)
    })

    it(`confirms an original ${editor ? 'set' : 'detail'} value again after an ambiguous failed write`, async () => {
      const items = stubReads()
      vi.mocked(api.put).mockImplementationOnce(async (_url, data) => {
        Object.assign(items[0], data)
        throw new Error('Connection lost after the server saved')
      }).mockImplementation(async (_url, data) => { Object.assign(items[0], data); return response(items[0]) })
      mount(editor)
      const title = await screen.findByRole('textbox', { name: editor ? 'Title for 1' : 'Title' })
      fireEvent.change(title, { target: { value: 'Unacknowledged change' } }); fireEvent.blur(title)
      const retry = await screen.findByRole('button', { name: 'Retry save' })
      expect(items[0].title).toBe('Unacknowledged change')
      fireEvent.change(title, { target: { value: 'Control 1' } })
      fireEvent.click(retry)
      await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
      expect(items[0].title).toBe('Control 1')
    })

    it(`retains a failed ${editor ? 'set' : 'detail'} draft and retries the latest text explicitly`, async () => {
      const items = stubReads()
      vi.mocked(api.put).mockRejectedValueOnce(new Error('Offline')).mockImplementation(async (_url, data) => { Object.assign(items[0], data); return response(items[0]) })
      mount(editor)
      const title = await screen.findByRole('textbox', { name: editor ? 'Title for 1' : 'Title' })
      fireEvent.change(title, { target: { value: 'Retained draft' } }); fireEvent.blur(title)
      const retry = await screen.findByRole('button', { name: 'Retry save' })
      expect(title).toHaveValue('Retained draft')
      fireEvent.change(title, { target: { value: 'Latest retained draft' } }); fireEvent.blur(title)
      expect(api.put).toHaveBeenCalledTimes(1)
      fireEvent.click(retry)
      await waitFor(() => expect(items[0].title).toBe('Latest retained draft'))
    })
  }

  it('keeps metadata edited during a save and blocks submission until every draft is saved', async () => {
    const document = { id: 'd1', jurisdiction_id: 'dk', name: 'Certification controls', status: 'draft', document_type: 'annex_b' }
    stubReads(requirements(), document)
    const pending: Array<() => void> = []
    vi.mocked(api.put).mockImplementation((_url, data) => new Promise((resolve) => pending.push(() => { Object.assign(document, data); resolve(response({ ...document })) })))
    mount(true)
    await screen.findByRole('textbox', { name: 'Title for 1' })
    fireEvent.click(screen.getByText('Requirement set details'))
    const name = screen.getByRole('textbox', { name: 'Requirement Set Name' })
    fireEvent.change(name, { target: { value: 'First name' } }); fireEvent.blur(name)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    fireEvent.change(name, { target: { value: 'Latest name' } })
    expect(screen.getByRole('button', { name: 'Submit for Approval' })).toBeDisabled()
    await act(async () => pending.shift()!())
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(name).toHaveValue('Latest name')
    expect(screen.getByRole('button', { name: 'Submit for Approval' })).toBeDisabled()
    await act(async () => pending.shift()!())
    await waitFor(() => expect(screen.getByRole('button', { name: 'Submit for Approval' })).toBeEnabled())
    expect(document.name).toBe('Latest name')
    expect(vi.mocked(api.post).mock.calls.some(([url]) => /\/(submit|approve)$/.test(url))).toBe(false)
  })
})
