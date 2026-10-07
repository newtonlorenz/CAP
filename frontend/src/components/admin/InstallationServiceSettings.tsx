import { useEffect, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import { getApiErrorMessage } from '../../api/errors'
import Button from '../ui/Button'
import Card from '../ui/Card'
import LoadError from '../ui/LoadError'

type Metadata = { source: 'environment' | 'database'; revision: number }
type EmailFields = {
  mode: 'disabled' | 'smtp'
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_from: string
  smtp_security: 'starttls' | 'ssl' | 'none'
}
type AiFields = { provider: 'none' | 'openai' | 'anthropic'; model: string }
type EmailSettings = EmailFields & Metadata & { password_configured: boolean }
type AiSettings = AiFields & Metadata & { api_key_configured: boolean; credential_provider: 'openai' | 'anthropic' | null }
type JevFields = { enabled: boolean; model: string }
type JevSettings = JevFields & Metadata & { api_key_configured: boolean }
type InstallationSettings = { email: EmailSettings; ai: AiSettings; jev: JevSettings }
type TestResult = { ok: boolean; message: string }
const inputClass = 'w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:outline-accent'

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return <div className="flex flex-col gap-1"><label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>{children}</div>
}

function ServiceForm<T extends EmailFields | AiFields | JevFields>({
  kind, saved, fields, credentialConfigured, credentialProvider, enabled, replacementRequired, children, reload,
}: {
  kind: 'email' | 'ai' | 'jev'
  saved: T & Metadata
  fields: (value: T) => T
  credentialConfigured: boolean
  credentialProvider?: string | null
  enabled: (value: T) => boolean
  replacementRequired: (draft: T, baseline: T) => boolean
  children: (draft: T, update: (patch: Partial<T>) => void) => ReactNode
  reload: () => Promise<T & Metadata>
}) {
  const queryClient = useQueryClient()
  const [baseline, setBaseline] = useState(saved)
  const [draft, setDraft] = useState(() => fields(saved))
  const [credential, setCredential] = useState('')
  const [clearCredential, setClearCredential] = useState(false)
  const [busy, setBusy] = useState<'save' | 'test' | 'reload' | null>(null)
  const [message, setMessage] = useState<TestResult | null>(null)
  const [conflict, setConflict] = useState(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(fields(baseline)) || !!credential.trim() || clearCredential
  const needsReplacement = credentialConfigured && replacementRequired(draft, baseline)
  const secretLabel = kind === 'email' ? 'SMTP password' : 'API key'
  const edit = () => setMessage(null)

  useEffect(() => {
    if (!dirty && !conflict && saved.revision >= baseline.revision) {
      setBaseline(saved)
      setDraft(fields(saved))
    }
  }, [saved, dirty, conflict, fields, baseline.revision])

  const save = async () => {
    if (busy || conflict || !dirty) return
    setBusy('save')
    setMessage(null)
    try {
      const response = await api.put<T & Metadata>(`/admin/installation-settings/${kind}`, {
        ...draft,
        revision: baseline.revision,
        ...(clearCredential ? { [kind === 'email' ? 'clear_password' : 'clear_api_key']: true }
          : credential.trim() ? { [kind === 'email' ? 'password' : 'api_key']: credential } : {}),
      })
      setBaseline(response.data)
      setDraft(fields(response.data))
      setCredential('')
      setClearCredential(false)
      queryClient.setQueryData<InstallationSettings>(['installation-settings'], current => current ? { ...current, [kind]: response.data } : current)
      void queryClient.invalidateQueries({ queryKey: ['installation-capabilities'] })
      setMessage({ ok: true, message: 'Settings saved. You can now test the saved configuration.' })
    } catch (error) {
      if ((error as { response?: { status?: number } }).response?.status === 409) {
        setConflict(true)
        setMessage({ ok: false, message: 'These settings changed since you loaded them. Reload the latest saved settings, review your draft, then save again. Your draft has been kept.' })
      } else {
        setMessage({ ok: false, message: getApiErrorMessage(error, 'Settings could not be saved. Your draft has been kept; try again.') })
      }
    } finally {
      setBusy(null)
    }
  }

  const test = async () => {
    if (busy || dirty || conflict || !enabled(draft)) return
    setBusy('test')
    setMessage(null)
    try {
      const response = await api.post<TestResult>(`/admin/installation-settings/${kind}/test`)
      setMessage(response.data)
    } catch (error) {
      setMessage({ ok: false, message: getApiErrorMessage(error, 'The test could not be completed. Check your connection and try again.') })
    } finally {
      setBusy(null)
    }
  }

  const refresh = async () => {
    setBusy('reload')
    try {
      const latest = await reload()
      setBaseline(latest)
      setConflict(false)
      setMessage({ ok: true, message: 'Latest saved settings loaded. Your draft has been kept. Review it before saving; it will replace the saved settings.' })
    } catch {
      setMessage({ ok: false, message: 'The latest settings could not be loaded. Your draft has been kept; try again.' })
    } finally {
      setBusy(null)
    }
  }

  return <form className="space-y-4" onSubmit={event => { event.preventDefault(); void save() }}>
    <p className="text-xs text-muted">Current source: {saved.source === 'environment' ? 'Server environment' : 'Saved in CAP'}. Changes apply across this installation.</p>
    <fieldset disabled={!!busy} className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{children(draft, patch => { edit(); setDraft(current => ({ ...current, ...patch })) })}</div>
      <Field label={secretLabel} id={`${kind}-credential`}>
        <input id={`${kind}-credential`} type="password" autoComplete="new-password" className={inputClass} value={credential} disabled={clearCredential}
          onChange={event => { edit(); setCredential(event.target.value) }} aria-describedby={`${kind}-credential-help`} />
      </Field>
      <p id={`${kind}-credential-help`} className="text-xs text-muted">{credentialConfigured ? `${secretLabel} configured${credentialProvider ? ` for ${credentialProvider}` : ''}. Leave blank to keep it.` : `No ${secretLabel.toLowerCase()} configured.`}</p>
      {credentialConfigured && <label className="flex items-center gap-2 text-sm text-ink"><input type="checkbox" checked={clearCredential} onChange={event => { edit(); setClearCredential(event.target.checked) }} />Remove saved {secretLabel.toLowerCase()}</label>}
      {needsReplacement && <p className="text-sm text-muted">{kind === 'email' ? 'Changing the SMTP server, port, security or username requires a replacement password, or explicit removal of the saved password.' : 'Changing AI provider requires a replacement API key, or explicit removal of the saved key.'}</p>}
      {dirty && <p className="text-sm text-muted">Save changes before testing.</p>}
      {!enabled(draft) && <p className="text-sm text-muted">{kind === 'email' ? 'Email delivery is disabled.' : kind === 'jev' ? 'Jev enhancement is disabled.' : 'AI is disabled.'}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        {conflict && <Button onClick={() => void refresh()}>Reload saved settings and keep draft</Button>}
        <Button onClick={() => void test()} loading={busy === 'test'} disabled={dirty || conflict || !enabled(draft)}>{kind === 'email' ? 'Send test email to me' : kind === 'jev' ? 'Test Jev connection' : 'Test AI connection'}</Button>
        <Button type="submit" variant="primary" loading={busy === 'save'} disabled={!dirty || conflict || (needsReplacement && !credential.trim() && !clearCredential)}>Save changes</Button>
      </div>
    </fieldset>
    {message && <p role={message.ok ? 'status' : 'alert'} className={`rounded-md border p-3 text-sm ${message.ok ? 'border-line bg-canvas text-ink' : 'border-danger-line bg-danger-soft text-danger'}`}>{message.message}</p>}
  </form>
}

const emailFields = (value: EmailFields): EmailFields => ({ mode: value.mode, smtp_host: value.smtp_host, smtp_port: value.smtp_port, smtp_user: value.smtp_user, smtp_from: value.smtp_from, smtp_security: value.smtp_security })
const aiFields = (value: AiFields): AiFields => ({ provider: value.provider, model: value.model })

const jevFields = (value: JevFields): JevFields => ({ enabled: value.enabled, model: value.model })

export default function InstallationServiceSettings({ section, isSystemAdmin, userEmail }: { section: string; isSystemAdmin: boolean; userEmail: string }) {
  const settings = useQuery({
    queryKey: ['installation-settings'],
    enabled: isSystemAdmin,
    queryFn: async () => (await api.get<InstallationSettings>('/admin/installation-settings')).data,
  })
  const reload = async () => {
    const result = await settings.refetch()
    if (result.error) throw result.error
    if (!result.data) throw new Error('Settings unavailable')
    return result.data
  }
  return <>{(['email', 'ai'] as const).map(kind => <section data-tour={`settings-${kind}`} key={kind} hidden={section !== kind} aria-label={`${kind === 'email' ? 'Email' : 'AI'} settings`}>
    <Card className="p-4 sm:p-5">
      <h2 className="text-lg font-semibold text-ink">{kind === 'email' ? 'Email' : 'AI'}</h2>
      {!isSystemAdmin ? <p className="mt-2 text-sm text-muted">These settings are shared across the installation. Only system admins can manage them. Contact a system admin to make changes. You can manage your company's Jira connection in Jira integration.</p> : <>
        <p className="mt-1 mb-4 text-sm text-muted">{kind === 'email' ? 'Used for review reminders and comment mentions. Product-feedback notifications are managed separately.' : 'Choose the provider and model used for AI assistance across this installation.'}</p>
        {settings.isError && !settings.data ? <LoadError subject={`${kind === 'email' ? 'Email' : 'AI'} settings`} onRetry={() => void settings.refetch()} /> : !settings.data?.[kind] ? <p className="text-sm text-muted">Loading settings…</p> : kind === 'email' ? <>
          <p className="mb-4 text-xs text-muted">The test sends an email using the saved configuration to your signed-in address: {userEmail}.</p>
          <ServiceForm kind="email" saved={settings.data.email} fields={emailFields} credentialConfigured={settings.data.email.password_configured} enabled={value => value.mode === 'smtp'} reload={async () => (await reload()).email}
            replacementRequired={(draft, baseline) => draft.smtp_host !== baseline.smtp_host || draft.smtp_port !== baseline.smtp_port || draft.smtp_user !== baseline.smtp_user || draft.smtp_security !== baseline.smtp_security}>
            {(draft, update) => <>
              <Field label="Email delivery" id="email-mode"><select id="email-mode" className={inputClass} value={draft.mode} onChange={e => update({ mode: e.target.value as EmailFields['mode'] })}><option value="disabled">Disabled</option><option value="smtp">SMTP</option></select></Field>
              <Field label="SMTP host" id="email-host"><input id="email-host" className={inputClass} required={draft.mode === 'smtp'} value={draft.smtp_host} onChange={e => update({ smtp_host: e.target.value })} /></Field>
              <Field label="SMTP port" id="email-port"><input id="email-port" type="number" min="1" max="65535" required className={inputClass} value={draft.smtp_port} onChange={e => update({ smtp_port: Number(e.target.value) })} /></Field>
              <Field label="Connection security" id="email-security"><select id="email-security" className={inputClass} value={draft.smtp_security} onChange={e => update({ smtp_security: e.target.value as EmailFields['smtp_security'] })}><option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option><option value="none">None</option></select></Field>
              <Field label="SMTP username" id="email-user"><input id="email-user" className={inputClass} value={draft.smtp_user} autoComplete="off" onChange={e => update({ smtp_user: e.target.value })} /></Field>
              <Field label="From email address" id="email-from"><input id="email-from" type="email" required={draft.mode === 'smtp'} className={inputClass} value={draft.smtp_from} onChange={e => update({ smtp_from: e.target.value })} /></Field>
            </>}
          </ServiceForm>
        </> : <>
          <p className="mb-4 text-xs text-muted">Testing sends a small synthetic request using the saved configuration. No documents are sent. Your provider may charge for this API usage.</p>
          <ServiceForm kind="ai" saved={settings.data.ai} fields={aiFields} credentialConfigured={settings.data.ai.api_key_configured} credentialProvider={settings.data.ai.credential_provider} enabled={value => value.provider !== 'none'} reload={async () => (await reload()).ai}
            replacementRequired={draft => draft.provider !== 'none' && draft.provider !== settings.data.ai.credential_provider}>
            {(draft, update) => <>
              <Field label="AI provider" id="ai-provider"><select id="ai-provider" className={inputClass} value={draft.provider} onChange={e => update({ provider: e.target.value as AiFields['provider'] })}><option value="none">Disabled</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option></select></Field>
              <Field label="Model" id="ai-model"><input id="ai-model" className={inputClass} required={draft.provider !== 'none'} value={draft.model} onChange={e => update({ model: e.target.value })} /></Field>
            </>}
          </ServiceForm>
        </>}
      </>}
    </Card>
  </section>)}
    <section hidden={section !== 'ai'} aria-label="Jev enhancement settings" className="mt-4">
      <Card className="p-4 sm:p-5">
        <h2 className="text-lg font-semibold text-ink">Jev enhancement</h2>
        <p className="mt-1 mb-4 text-sm text-muted">Optional source checks and suggestions for requirements and form imports. Existing extraction works independently. Selected checks send source text to TypeSafe.</p>
        {!isSystemAdmin ? <p className="text-sm text-muted">Only system admins can manage these installation settings.</p> : settings.isError && !settings.data ? <LoadError subject="Jev settings" onRetry={() => void settings.refetch()} /> : !settings.data?.jev ? <p className="text-sm text-muted">Loading settings…</p> : <>
          <p className="mb-4 text-xs text-muted">Testing sends only synthetic data. TypeSafe may charge for this API usage.</p>
          <ServiceForm kind="jev" saved={settings.data.jev} fields={jevFields} credentialConfigured={settings.data.jev.api_key_configured} enabled={value => value.enabled} reload={async () => (await reload()).jev} replacementRequired={() => false}>
            {(draft, update) => <>
              <Field label="Jev enhancement" id="jev-enabled"><select id="jev-enabled" className={inputClass} value={draft.enabled ? 'enabled' : 'disabled'} onChange={e => update({ enabled: e.target.value === 'enabled' })}><option value="disabled">Disabled</option><option value="enabled">Enabled</option></select></Field>
              <Field label="Model" id="jev-model"><input id="jev-model" className={inputClass} required value={draft.model} onChange={e => update({ model: e.target.value })} /></Field>
            </>}
          </ServiceForm>
        </>}
      </Card>
    </section>
  </>
}
