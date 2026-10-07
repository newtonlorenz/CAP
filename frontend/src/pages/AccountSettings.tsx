import { useState, type FormEvent, type InputHTMLAttributes } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import { useAuth } from '../contexts/AuthContext'
import { useDraftNavigationGuard } from '../hooks/useDraftNavigationGuard'
import Button from '../components/ui/Button'
import SectionNav from '../components/ui/SectionNav'
import PageHeading from '../components/ui/PageHeading'

type NotificationSettings = { review_mentions: boolean; review_reminders: boolean }
const inputClass = 'mt-2 block w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent'

function PasswordField({ label, id, visible, onToggle, ...inputProps }: InputHTMLAttributes<HTMLInputElement> & { label: string; id: string; visible: boolean; onToggle: () => void }) {
  return <div>
    <label htmlFor={id} className="block text-sm font-medium text-ink">{label}</label>
    <div className="mt-2 flex items-stretch gap-2">
      <input {...inputProps} id={id} type={visible ? 'text' : 'password'} className="min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink" />
      <button type="button" onClick={onToggle} aria-label={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`} aria-controls={id} aria-pressed={visible} className="min-h-10 rounded-lg border border-line-strong px-3 text-sm font-semibold text-ink">{visible ? 'Hide' : 'Show'}</button>
    </div>
  </div>
}

export default function AccountSettings() {
  const { user, refreshUser } = useAuth()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const section = params.get('section') === 'notifications' ? 'notifications' : 'account'
  const [fullName, setFullName] = useState(user?.full_name || '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [visiblePasswords, setVisiblePasswords] = useState<Record<string, boolean>>({})
  const togglePassword = (field: string) => setVisiblePasswords(current => ({ ...current, [field]: !current[field] }))
  const [passwordError, setPasswordError] = useState('')
  const [passwordSaved, setPasswordSaved] = useState(false)
  const [notificationDraft, setNotificationDraft] = useState<NotificationSettings | null>(null)
  const notifications = useQuery({ queryKey: ['notification-settings', user?.id], queryFn: async () => (await api.get<NotificationSettings>('/auth/notification-settings')).data })
  const profile = useMutation({
    mutationFn: () => api.patch<{ full_name: string }>('/auth/me', { full_name: fullName.trim() }),
    onSuccess: async (response) => { setFullName(response.data.full_name); await refreshUser() },
  })
  const password = useMutation({
    mutationFn: () => api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword }),
    onSuccess: () => { setCurrentPassword(''); setNewPassword(''); setConfirmation(''); setVisiblePasswords({}); setPasswordSaved(true) },
  })
  const saveNotifications = useMutation({
    mutationFn: (value: NotificationSettings) => api.patch<NotificationSettings>('/auth/notification-settings', value),
    onSuccess: (response) => { queryClient.setQueryData(['notification-settings', user?.id], response.data); setNotificationDraft(null) },
  })
  const notificationValue = notificationDraft || notifications.data
  const notificationsDirty = !!notificationDraft && (notificationDraft.review_mentions !== notifications.data?.review_mentions || notificationDraft.review_reminders !== notifications.data?.review_reminders)
  const profileDirty = fullName !== (user?.full_name || '')
  useDraftNavigationGuard(profileDirty || !!currentPassword || !!newPassword || !!confirmation || notificationsDirty || profile.isPending || password.isPending || saveNotifications.isPending)

  const changePassword = (event: FormEvent) => {
    event.preventDefault()
    setPasswordError('')
    setPasswordSaved(false)
    if (newPassword !== confirmation) { setPasswordError('The new passwords do not match.'); return }
    if (new TextEncoder().encode(newPassword).length > 72) { setPasswordError('Use a password of no more than 72 UTF-8 bytes.'); return }
    password.mutate()
  }

  return <div className="cap-account-page mx-auto max-w-5xl">
    <PageHeading title="My account" description="Manage your profile, password and email notifications." />
    <SectionNav label="Account settings sections" value={section} items={[{ id: 'account', label: 'Account settings' }, { id: 'notifications', label: 'Notifications' }]} onChange={value => setParams({ section: value })} />
    <div hidden={section !== 'account'} className="cap-panel mt-5 px-6">
      <section data-tour="account-profile" className="border-b border-line py-6">
        <h2 className="text-lg font-semibold text-ink">Profile</h2>
        <form className="mt-4 max-w-md space-y-4" onSubmit={event => { event.preventDefault(); profile.mutate() }}>
          <label className="block text-sm font-medium text-ink">Full name<input className={inputClass} autoComplete="name" required maxLength={255} value={fullName} disabled={profile.isPending} onChange={event => { setFullName(event.target.value); profile.reset() }} /></label>
          <div><span className="text-sm font-medium text-ink">Email address</span><p className="mt-2 break-words text-sm text-muted">{user?.email}</p><p className="mt-1 text-xs text-muted">Contact your administrator to change your sign-in email.</p></div>
          <div><span className="text-sm font-medium text-ink">Role</span><p className="mt-2 text-sm capitalize text-muted">{user?.role.replace(/_/g, ' ')}</p></div>
          {profile.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(profile.error, 'Your profile could not be saved. Try again.')}</p>}
          {profile.isSuccess && <p role="status" className="text-sm text-success">Profile saved.</p>}
          <Button type="submit" variant="primary" loading={profile.isPending} disabled={!profileDirty || !fullName.trim()}>Save profile</Button>
        </form>
      </section>
      <section data-tour="account-password" className="py-6">
        <h2 className="text-lg font-semibold text-ink">Change password</h2>
        <p className="mt-2 text-sm text-muted">Use at least 8 characters. Changing your password signs out your other sessions.</p>
        <form className="mt-4 max-w-md space-y-4" onSubmit={changePassword}>
          <fieldset disabled={password.isPending} className="space-y-4">
            <PasswordField label="Current password" id="current-password" visible={!!visiblePasswords.current} onToggle={() => togglePassword('current')} autoComplete="current-password" required maxLength={256} value={currentPassword} onChange={event => { setCurrentPassword(event.target.value); setPasswordSaved(false); password.reset() }} />
            <PasswordField label="New password" id="new-password" visible={!!visiblePasswords.new} onToggle={() => togglePassword('new')} autoComplete="new-password" required minLength={8} maxLength={72} value={newPassword} onChange={event => { setNewPassword(event.target.value); setPasswordError(''); setPasswordSaved(false); password.reset() }} />
            <PasswordField label="Confirm new password" id="confirm-password" visible={!!visiblePasswords.confirm} onToggle={() => togglePassword('confirm')} autoComplete="new-password" required value={confirmation} onChange={event => { setConfirmation(event.target.value); setPasswordError(''); setPasswordSaved(false) }} />
          </fieldset>
          {(passwordError || password.isError) && <p role="alert" className="text-sm text-danger">{passwordError || getApiErrorMessage(password.error, 'Your password could not be changed. Try again.')}</p>}
          {passwordSaved && <p role="status" className="text-sm text-success">Password changed. You are still signed in on this browser.</p>}
          <Button type="submit" variant="primary" loading={password.isPending}>Change password</Button>
        </form>
      </section>
    </div>
    <section data-tour="account-notifications" hidden={section !== 'notifications'} className="cap-panel mt-5 p-6">
      <h2 className="text-lg font-semibold text-ink">Email notifications</h2>
      <p className="mt-2 text-sm text-muted">Choose which review emails you receive. These settings apply across your devices.</p>
      {notifications.isPending && <p role="status" className="mt-4 text-sm text-muted">Loading notification settings…</p>}
      {notifications.isError && <div role="alert" className="mt-4 text-sm text-danger">Notification settings could not be loaded. <Button onClick={() => notifications.refetch()}>Retry</Button></div>}
      {notificationValue && <form className="mt-6 space-y-5" onSubmit={event => { event.preventDefault(); saveNotifications.mutate(notificationValue) }}>
        <fieldset disabled={saveNotifications.isPending} className="space-y-5">
          {([{ key: 'review_mentions', title: 'Mentions in review comments', description: 'Email me when someone mentions me in a review comment.' }, { key: 'review_reminders', title: 'Review reminders', description: 'Email me when a manager sends a reminder about my assigned review work.' }] as const).map(item => <label key={item.key} className="flex cursor-pointer items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1 h-4 w-4 accent-brand" checked={notificationValue[item.key]} onChange={event => { setNotificationDraft({ ...notificationValue, [item.key]: event.target.checked }); saveNotifications.reset() }} />
            <span><span className="block font-semibold text-ink">{item.title}</span><span className="mt-1 block text-muted">{item.description}</span></span>
          </label>)}
        </fieldset>
        {saveNotifications.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(saveNotifications.error, 'Notification settings could not be saved. Try again.')}</p>}
        {saveNotifications.isSuccess && <p role="status" className="text-sm text-success">Notification settings saved.</p>}
        <Button type="submit" variant="primary" loading={saveNotifications.isPending} disabled={!notificationsDirty}>Save notification settings</Button>
      </form>}
    </section>
  </div>
}
