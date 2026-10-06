import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const auth = vi.hoisted(() => ({ installationOperator: true }))
vi.mock('../api/client', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { role: 'admin', installation_operator: auth.installationOperator, email: 'admin@example.com' }, logout: vi.fn() }) }))
vi.mock('../contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
import api from '../api/client'
import Settings from '../pages/admin/Settings'

const replacementPassword = crypto.randomUUID()
const replacementKey = crypto.randomUUID()
const draftKey = crypto.randomUUID()

const initial = {
  email: { mode: 'smtp', smtp_host: 'smtp.example.com', smtp_port: 587, smtp_user: 'mailer', smtp_from: 'cap@example.com', smtp_security: 'starttls', password_configured: true, source: 'environment', revision: 0 },
  ai: { provider: 'openai', model: 'configured-model', api_key_configured: true, credential_provider: 'openai', source: 'environment', revision: 0 },
}
let saved = structuredClone(initial)

function renderSettings(section = 'email') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[`/admin/settings?section=${section}`]}><Settings /></MemoryRouter></QueryClientProvider>)
  return queryClient
}

beforeEach(() => {
  vi.resetAllMocks()
  auth.installationOperator = true
  saved = structuredClone(initial)
  vi.mocked(api.get).mockImplementation(async url => ({ data: url === '/admin/installation-settings' ? saved : url === '/integrations/jira' ? { configured: false, integration: null } : { items: [] } }))
  vi.mocked(api.put).mockImplementation(async (url, body) => {
    const kind = url.endsWith('/email') ? 'email' : 'ai'
    const { clear_password, clear_api_key, ...fields } = body as Record<string, unknown> & { revision: number }
    delete fields.password
    delete fields.api_key
    const next = { ...saved[kind], ...fields, revision: fields.revision + 1, source: 'database', ...(clear_password ? { password_configured: false } : {}), ...(clear_api_key ? { api_key_configured: false } : {}) }
    saved = { ...saved, [kind]: next }
    return { data: next }
  })
  vi.mocked(api.post).mockResolvedValue({ data: { ok: true, message: 'Test completed successfully.' } })
})

describe('installation service settings', () => {
  it('retains the saved password on public-field saves and tests only saved settings', async () => {
    const queryClient = renderSettings()
    const invalidation = vi.spyOn(queryClient, 'invalidateQueries')
    const sender = await screen.findByLabelText('From email address')
    expect(screen.getByText(/signed-in address: admin@example.com/)).toBeVisible()
    expect(screen.getAllByText(/Current source: Server environment/)[0]).toBeVisible()
    expect(screen.getByLabelText('SMTP password')).toHaveValue('')
    fireEvent.change(sender, { target: { value: 'updated@example.com' } })
    expect(screen.getByRole('button', { name: 'Send test email to me' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('status')
    expect(api.put).toHaveBeenCalledWith('/admin/installation-settings/email', {
      mode: 'smtp', smtp_host: 'smtp.example.com', smtp_port: 587, smtp_user: 'mailer', smtp_from: 'updated@example.com', smtp_security: 'starttls', revision: 0,
    })
    expect(invalidation).toHaveBeenCalledWith({ queryKey: ['installation-capabilities'] })
    fireEvent.click(screen.getByRole('button', { name: 'Send test email to me' }))
    expect(await screen.findByText('Test completed successfully.')).toBeVisible()
    expect(api.post).toHaveBeenCalledWith('/admin/installation-settings/email/test')
    fireEvent.change(sender, { target: { value: 'another@example.com' } })
    expect(screen.queryByText('Test completed successfully.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send test email to me' })).toBeDisabled()
  })

  it('keeps both drafts across tabs and clears a replacement credential only after a successful save', async () => {
    renderSettings()
    fireEvent.change(await screen.findByLabelText('SMTP host'), { target: { value: 'draft.example.com' } })
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('SMTP password'), { target: { value: replacementPassword } })
    fireEvent.click(screen.getByRole('button', { name: 'AI' }))
    fireEvent.change(screen.getByLabelText('AI provider'), { target: { value: 'anthropic' } })
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'new-model' } })
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: replacementKey } })
    fireEvent.click(screen.getByRole('button', { name: 'Email' }))
    expect(screen.getByLabelText('SMTP host')).toHaveValue('draft.example.com')
    expect(screen.getByLabelText('SMTP password')).toHaveValue(replacementPassword)
    vi.mocked(api.put).mockRejectedValueOnce(new Error('Network unavailable'))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('SMTP password')).toHaveValue(replacementPassword)
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.getByLabelText('SMTP password')).toHaveValue(''))
    expect(api.put).toHaveBeenLastCalledWith('/admin/installation-settings/email', expect.objectContaining({ password: replacementPassword, smtp_host: 'draft.example.com' }))
    fireEvent.click(screen.getByRole('button', { name: 'AI' }))
    expect(screen.getByLabelText('Model')).toHaveValue('new-model')
    expect(screen.getByLabelText('API key')).toHaveValue(replacementKey)
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.getByLabelText('API key')).toHaveValue(''))
    expect(api.put).toHaveBeenLastCalledWith('/admin/installation-settings/ai', { provider: 'anthropic', model: 'new-model', revision: 0, api_key: replacementKey })
  })

  it('requires explicit credential removal and keeps AI tests disabled when AI is disabled', async () => {
    renderSettings('ai')
    await screen.findByLabelText('Model')
    fireEvent.change(screen.getByLabelText('AI provider'), { target: { value: 'none' } })
    fireEvent.click(screen.getByLabelText('Remove saved api key'))
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('status')
    expect(api.put).toHaveBeenCalledWith('/admin/installation-settings/ai', { provider: 'none', model: 'configured-model', revision: 0, clear_api_key: true })
    expect(screen.getByRole('button', { name: 'Test AI connection' })).toBeDisabled()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('retains the provider-bound AI key while disabled and allows the same provider to be re-enabled', async () => {
    renderSettings('ai')
    await screen.findByLabelText('AI provider')
    fireEvent.change(screen.getByLabelText('AI provider'), { target: { value: 'none' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('status')
    expect(screen.getByLabelText('AI provider')).toHaveValue('none')
    expect(screen.getByRole('button', { name: 'Test AI connection' })).toBeDisabled()
    expect(screen.getByText('API key configured for openai. Leave blank to keep it.')).toBeVisible()
    expect(api.put).toHaveBeenLastCalledWith('/admin/installation-settings/ai', { provider: 'none', model: 'configured-model', revision: 0 })
    fireEvent.change(screen.getByLabelText('AI provider'), { target: { value: 'anthropic' } })
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('AI provider'), { target: { value: 'openai' } })
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('status')
    expect(api.put).toHaveBeenLastCalledWith('/admin/installation-settings/ai', { provider: 'openai', model: 'configured-model', revision: 1 })
  })

  it('reports AI test failures and request errors, and clears results after an edit', async () => {
    renderSettings('ai')
    await screen.findByLabelText('Model')
    expect(screen.getByText(/provider may charge/)).toBeVisible()
    vi.mocked(api.post).mockResolvedValueOnce({ data: { ok: false, message: 'Provider rejected the saved key.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test AI connection' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Provider rejected the saved key.')
    expect(api.post).toHaveBeenCalledWith('/admin/installation-settings/ai/test')
    vi.mocked(api.post).mockRejectedValueOnce(new Error('Network unavailable'))
    fireEvent.click(screen.getByRole('button', { name: 'Test AI connection' }))
    await waitFor(() => expect(screen.getByRole('alert')).not.toHaveTextContent('Provider rejected'))
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'draft-model' } })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Test AI connection' })).toBeDisabled()
  })

  it('preserves the draft through a conflict and reloads the revision before another save', async () => {
    renderSettings('ai')
    fireEvent.change(await screen.findByLabelText('Model'), { target: { value: 'my-draft' } })
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: draftKey } })
    vi.mocked(api.put).mockRejectedValueOnce({ response: { status: 409 } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your draft has been kept')
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    saved = { ...saved, ai: { ...saved.ai, model: 'someone-elses-model', revision: 7 } }
    fireEvent.click(screen.getByRole('button', { name: 'Reload saved settings and keep draft' }))
    await screen.findByText(/Latest saved settings loaded/)
    expect(screen.getByLabelText('Model')).toHaveValue('my-draft')
    expect(screen.getByLabelText('API key')).toHaveValue(draftKey)
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(api.put).toHaveBeenLastCalledWith('/admin/installation-settings/ai', { provider: 'openai', model: 'my-draft', revision: 7, api_key: draftKey }))
  })

  it.each(['email', 'ai'])('shows restricted company-admin direct links without shared settings requests or forms: %s', async section => {
    auth.installationOperator = false
    renderSettings(section)
    const region = screen.getByRole('region', { name: `${section === 'email' ? 'Email' : 'AI'} settings` })
    expect(within(region).getByText(/Only system admins/)).toBeVisible()
    expect(within(region).queryByRole('button')).not.toBeInTheDocument()
    expect(within(region).queryByRole('textbox')).not.toBeInTheDocument()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/integrations/jira'))
    expect(api.get).not.toHaveBeenCalledWith('/admin/installation-settings')
    expect(api.get).not.toHaveBeenCalledWith('/admin/backups')
  })
})
