import { Link, useSearchParams } from 'react-router-dom'
import SectionNav from '../../components/ui/SectionNav'
import InstallationServiceSettings from '../../components/admin/InstallationServiceSettings'
import { formatDateTime } from '../../utils/dateFormat'
import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import type {
  BackupListResponse,
  BackupMetadata,
  BackupRestoreResponse,
  JiraIntegrationEnvelope,
} from '../../types'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import { notifyApiError } from '../../utils/notify'
import Button from '../../components/ui/Button'
import LoadError from '../../components/ui/LoadError'
import Card from '../../components/ui/Card'
import DecisionModal from '../../components/ui/DecisionModal'
import { Table, TBody, TD, TH, THead, TR, TableEmpty } from '../../components/ui/Table'

type JiraFormState = {
  base_url: string
  project_key: string
  user_email: string
  api_token: string
  enabled: boolean
}

const defaultFormState: JiraFormState = {
  base_url: '',
  project_key: '',
  user_email: '',
  api_token: '',
  enabled: true,
}


const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

export default function Settings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedSection = searchParams.get('section') || 'jira'
  const settingsSection = ['jira', 'backups', 'email', 'ai'].includes(requestedSection) ? requestedSection : 'jira'
  const { logout, user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const isSystemAdmin = isAdmin && !!user?.installation_operator
  const toast = useToast()
  const queryClient = useQueryClient()
  const backupImportInputRef = useRef<HTMLInputElement | null>(null)
  const jiraDirty = useRef(false)
  const [jiraForm, setJiraForm] = useState<JiraFormState>(defaultFormState)
  const [downloadingBackupId, setDownloadingBackupId] = useState<string | null>(null)
  const [deletingBackupId, setDeletingBackupId] = useState<string | null>(null)
  const [restoreTarget, setRestoreTarget] = useState<BackupMetadata | null>(null)
  const [restoreConfirmation, setRestoreConfirmation] = useState('')

  const { data: jiraEnvelope, isLoading, isError: jiraError, refetch: retryJira } = useQuery({
    queryKey: ['jira-integration'],
    enabled: isAdmin,
    queryFn: async () => {
      const response = await api.get<JiraIntegrationEnvelope>('/integrations/jira')
      return response.data
    },
  })
  const { data: backupsEnvelope, isLoading: backupsLoading, isError: backupsError, refetch: retryBackups } = useQuery({
    queryKey: ['admin-backups'],
    enabled: isSystemAdmin,
    queryFn: async () => {
      const response = await api.get<BackupListResponse>('/admin/backups')
      return response.data
    },
  })

  const jiraIntegration = jiraEnvelope?.integration || null
  const backups = backupsEnvelope?.items || []

  useEffect(() => {
    if (jiraDirty.current) return
    setJiraForm({
      base_url: jiraIntegration?.base_url || '',
      project_key: jiraIntegration?.project_key || '',
      user_email: jiraIntegration?.user_email || '',
      api_token: '',
      enabled: jiraIntegration ? jiraIntegration.enabled : true,
    })
  }, [jiraIntegration])

  const saveJiraMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        base_url: jiraForm.base_url.trim(),
        project_key: jiraForm.project_key.trim(),
        user_email: jiraForm.user_email.trim(),
        api_token: jiraForm.api_token.trim() || undefined,
        enabled: jiraForm.enabled,
      }
      await api.put('/integrations/jira', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jira-integration'] })
      toast.success('Jira integration saved')
      jiraDirty.current = false
      setJiraForm((prev) => ({ ...prev, api_token: '' }))
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to save Jira integration')
    },
  })

  const testJiraMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        base_url: jiraForm.base_url.trim(),
        project_key: jiraForm.project_key.trim(),
        user_email: jiraForm.user_email.trim(),
        api_token: jiraForm.api_token.trim() || undefined,
      }
      const response = await api.post<{ ok: boolean; message: string }>(
        '/integrations/jira/test',
        payload
      )
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['jira-integration'] })
      if (data.ok) {
        toast.success(data.message || 'Jira connection successful')
      } else {
        toast.error(data.message || 'Jira connection failed')
      }
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to test Jira integration')
    },
  })

  const createBackupMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<BackupMetadata>('/admin/backups')
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-backups'] })
      toast.success('Backup created')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to create backup')
    },
  })

  const importBackupMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const response = await api.post<BackupMetadata>('/admin/backups/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return response.data
    },
    onSuccess: (backup) => {
      queryClient.invalidateQueries({ queryKey: ['admin-backups'] })
      toast.success('Backup imported', {
        description: `Imported ${backup.id}. Review the restore warning to continue.`,
      })
      setRestoreTarget(backup)
      setRestoreConfirmation('')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to import backup')
    },
    onSettled: () => {
      if (backupImportInputRef.current) {
        backupImportInputRef.current.value = ''
      }
    },
  })

  const deleteBackupMutation = useMutation({
    mutationFn: async (backupId: string) => {
      await api.delete(`/admin/backups/${backupId}`)
    },
    onMutate: (backupId) => {
      setDeletingBackupId(backupId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-backups'] })
      toast.success('Backup deleted')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to delete backup')
    },
    onSettled: () => {
      setDeletingBackupId(null)
    },
  })

  const restoreBackupMutation = useMutation({
    mutationFn: async (backupId: string) => {
      const response = await api.post<BackupRestoreResponse>(`/admin/backups/${backupId}/restore`, {
        confirmation: 'RESTORE',
      })
      return response.data
    },
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['admin-backups'] })
      setRestoreTarget(null)
      setRestoreConfirmation('')
      await logout()
      window.location.assign(`${import.meta.env.BASE_URL}login?restored=1`)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Restore failed')
    },
  })

  const downloadBackup = async (backupId: string, archiveFilename: string) => {
    setDownloadingBackupId(backupId)
    try {
      const response = await api.get(`/admin/backups/${backupId}/download`, { responseType: 'blob' })
      const blob = new Blob([response.data])
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = archiveFilename
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (error) {
      notifyApiError(toast, error, 'Failed to download backup')
    } finally {
      setDownloadingBackupId(null)
    }
  }

  const openImportDialog = () => {
    backupImportInputRef.current?.click()
  }

  const handleImportSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    importBackupMutation.mutate(file)
  }

  if (!isAdmin) return <Card className="p-5"><h1 className="text-xl font-semibold">Settings</h1><p className="mt-3 text-muted">Contact a company admin to manage your company's settings.</p></Card>

  return (
    <div className="min-w-0 space-y-4">
      <header className="py-1">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-ink">Settings</h1>
          <p className="mt-1 text-sm text-muted">
            Configure your company's Jira integration. System admins also manage shared email, AI, backups and restore.
          </p>
          <p className="mt-2 text-sm font-medium text-ink">Your access: {isSystemAdmin ? 'System admin' : 'Company admin'}</p>
          <Link to="/admin/users" className="mt-2 inline-block text-sm font-semibold text-accent underline">Manage your team</Link>
        </div>
      </header>

      <SectionNav label="Settings sections" value={settingsSection} items={[{id: 'jira', label: 'Jira integration'}, {id: 'email', label: 'Email'}, {id: 'ai', label: 'AI'}, {id: 'backups', label: 'Backups & restore'}]} onChange={value => setSearchParams(previous => { const next = new URLSearchParams(previous); next.set('section', value); return next })} />
      <section hidden={settingsSection !== 'jira'} aria-label="Jira integration settings">
      <Card className="p-4 sm:p-5">
        <div className="mb-4 min-w-0">
          <h2 className="text-lg font-semibold text-ink">Jira Integration</h2>
          <p className="mt-1 text-sm text-muted">
            Jira project connection used by your organization's review cycles.
          </p>
          <div className="mt-2 text-xs text-muted">
            Status:{' '}
            {jiraError ? 'Unavailable' : isLoading ? 'Loading…' : jiraIntegration
              ? jiraIntegration.enabled
                ? `Connected (${jiraIntegration.project_key})`
                : `Configured but disabled (${jiraIntegration.project_key})`
              : 'Not configured'}
          </div>
        </div>

        {jiraError ? <LoadError subject="Jira settings" onRetry={() => retryJira()} /> : isLoading ? (
          <div className="text-sm text-muted">Loading integration...</div>
        ) : (
          <form
            className="space-y-4"
            onChange={() => { jiraDirty.current = true }}
            onSubmit={(e) => {
              e.preventDefault()
              saveJiraMutation.mutate()
            }}
          >
            <fieldset disabled={saveJiraMutation.isPending || testJiraMutation.isPending} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1 sm:col-span-2">
                <label htmlFor="settings-field-1" className="text-sm font-medium text-ink">Jira site URL</label>
                <input id="settings-field-1"
                  type="url"
                  required
                  value={jiraForm.base_url}
                  onChange={(e) => setJiraForm((prev) => ({ ...prev, base_url: e.target.value }))}
                  placeholder="https://your-company.atlassian.net"
                  className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="settings-field-2" className="text-sm font-medium text-ink">Project key</label>
                <input id="settings-field-2"
                  type="text"
                  required
                  value={jiraForm.project_key}
                  onChange={(e) =>
                    setJiraForm((prev) => ({ ...prev, project_key: e.target.value.toUpperCase() }))
                  }
                  placeholder="PROJ"
                  className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="settings-field-3" className="text-sm font-medium text-ink">Jira account email</label>
                <input id="settings-field-3"
                  type="email"
                  required
                  value={jiraForm.user_email}
                  onChange={(e) => setJiraForm((prev) => ({ ...prev, user_email: e.target.value }))}
                  className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                />
              </div>
              <div className="flex flex-col gap-1 sm:col-span-2">
                <label htmlFor="settings-field-4" className="text-sm font-medium text-ink">
                  API token {jiraIntegration?.token_configured ? '(leave blank to keep current)' : ''}
                </label>
                <input id="settings-field-4"
                  type="password"
                  required={!jiraIntegration?.token_configured}
                  value={jiraForm.api_token}
                  onChange={(e) => setJiraForm((prev) => ({ ...prev, api_token: e.target.value }))}
                  placeholder={
                    jiraIntegration?.token_configured ? '••••••••••••' : 'Paste Jira API token'
                  }
                  className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                />
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={jiraForm.enabled}
                onChange={(e) => setJiraForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              />
              Enable Jira sync
            </label>

            <div className="rounded-md border border-line bg-canvas px-3 py-2 text-xs text-muted">
              {jiraIntegration?.last_tested_at ? (
                <>
                  Last test: {formatDateTime(jiraIntegration.last_tested_at)} (
                  {jiraIntegration.last_test_status || 'unknown'})<br />
                  {jiraIntegration.last_test_message || ''}
                </>
              ) : (
                'No connection test recorded yet.'
              )}
            </div>

            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <Button
                variant="secondary"
                type="button"
                loading={testJiraMutation.isPending}
                disabled={saveJiraMutation.isPending}
                onClick={(event) => { if (event.currentTarget.form?.reportValidity()) testJiraMutation.mutate() }}
              >
                Test connection
              </Button>
              <Button variant="primary" type="submit" loading={saveJiraMutation.isPending} disabled={testJiraMutation.isPending}>
                Save
              </Button>
            </div>
            </fieldset>
          </form>
        )}
      </Card>
      </section>

      <section hidden={settingsSection !== 'backups'} aria-label="Backup settings">
      {isSystemAdmin ? (
      <Card className="p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-ink">Backups & Restore</h2>
            <p className="mt-1 text-sm text-muted">
              Full-instance backups include database and uploads.
            </p>
            <p className="mt-1 text-xs text-muted">
              On a new server, authorise the temporary bootstrap administrator as a system
              admin before importing and restoring a `.capbak` file.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              ref={backupImportInputRef}
              type="file"
              accept=".capbak,application/octet-stream"
              className="hidden"
              onChange={handleImportSelection}
              aria-label="Import backup file"
            />
            <Button
              variant="secondary"
              loading={importBackupMutation.isPending}
              onClick={openImportDialog}
              disabled={createBackupMutation.isPending}
            >
              Import backup
            </Button>
            <Button
              variant="primary"
              loading={createBackupMutation.isPending}
              onClick={() => createBackupMutation.mutate()}
              disabled={importBackupMutation.isPending}
            >
              Create backup
            </Button>
          </div>
        </div>

        {backupsError ? <LoadError subject="Backups" onRetry={() => retryBackups()} /> : backupsLoading ? (
          <div className="text-sm text-muted">Loading backups...</div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <THead>
                <tr>
                  <TH>Created</TH>
                  <TH>Reason</TH>
                  <TH>Size</TH>
                  <TH>Checksum</TH>
                  <TH className="w-[1%]">Actions</TH>
                </tr>
              </THead>
              <TBody>
                {backups.map((backup) => {
                  const deleting = deletingBackupId === backup.id && deleteBackupMutation.isPending
                  const restoring =
                    restoreTarget?.id === backup.id && restoreBackupMutation.isPending
                  const downloading =
                    downloadingBackupId === backup.id && downloadingBackupId !== null

                  return (
                    <TR key={backup.id}>
                      <TD className="whitespace-nowrap text-ink">
                        {formatDateTime(backup.created_at)}
                      </TD>
                      <TD className="whitespace-nowrap text-ink">{backup.reason}</TD>
                      <TD className="whitespace-nowrap text-ink">
                        {formatSize(backup.size_bytes)}
                      </TD>
                      <TD className="font-mono text-xs text-muted">
                        {(backup.sha256 || '').slice(0, 12)}
                      </TD>
                      <TD>
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            loading={downloading}
                            onClick={() => downloadBackup(backup.id, backup.archive_filename)}
                            disabled={deleting || restoring}
                            aria-label={`Download backup ${backup.id}`}
                          >
                            Download
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => {
                              setRestoreTarget(backup)
                              setRestoreConfirmation('')
                            }}
                            disabled={deleting || restoring}
                            aria-label={`Restore backup ${backup.id}`}
                          >
                            Restore
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            loading={deleting}
                            onClick={() => deleteBackupMutation.mutate(backup.id)}
                            disabled={restoring}
                            aria-label={`Delete backup ${backup.id}`}
                          >
                            Delete
                          </Button>
                        </div>
                      </TD>
                    </TR>
                  )
                })}
                {backups.length === 0 ? (
                  <TableEmpty colSpan={5}>No backups yet.</TableEmpty>
                ) : null}
              </TBody>
            </Table>
          </div>
        )}
      </Card>
      ) : (
        <Card className="p-4 sm:p-5">
          <h2 className="text-lg font-semibold text-ink">Backups &amp; Restore</h2>
          <p className="mt-2 text-sm text-muted">Backups include the entire installation's database and uploads. Only system admins can create, import, download, delete or restore them.</p>
          <p className="mt-2 text-sm text-muted">Contact a system admin for backup or restore requests. You can manage your company's Jira connection in Jira integration.</p>
        </Card>
      )}
      </section>

      <InstallationServiceSettings section={settingsSection} isSystemAdmin={isSystemAdmin} userEmail={user?.email || ''} />

      <DecisionModal
        open={isSystemAdmin && !!restoreTarget}
        title="Restore backup?"
        description={`Restore backup "${restoreTarget?.id || ''}"?`}
        confirmLabel="Restore backup"
        confirmVariant="destructive"
        dangerDetails={[
          'Only restore a backup from a trusted source. Database restore can execute code.',
          'Replace the entire database and uploads with this backup.',
          'Create an automatic pre-restore safety backup first.',
          'Temporarily block non-backup API requests during restore.',
        ]}
        rationaleMode="required"
        rationaleLabel='Type RESTORE to confirm'
        rationalePlaceholder="RESTORE"
        rationaleValue={restoreConfirmation}
        onRationaleChange={setRestoreConfirmation}
        rationaleError={
          restoreConfirmation.length > 0 && restoreConfirmation !== 'RESTORE'
            ? 'Type RESTORE exactly to continue.'
            : null
        }
        confirmDisabled={restoreConfirmation !== 'RESTORE'}
        onConfirm={() => {
          if (!restoreTarget) return
          restoreBackupMutation.mutate(restoreTarget.id)
        }}
        onClose={() => {
          if (restoreBackupMutation.isPending) return
          setRestoreTarget(null)
          setRestoreConfirmation('')
        }}
        isWorking={restoreBackupMutation.isPending}
      />
    </div>
  )
}
