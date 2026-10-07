import '../workflow-pages.css'
import { formatDate, formatDateTime } from '../../utils/dateFormat'
import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import type { User, PaginatedResponse, AuditLogDetail, LoginHistoryEntry } from '../../types'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import { notifyApiError } from '../../utils/notify'
import Badge from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import LoadError from '../../components/ui/LoadError'
import Card from '../../components/ui/Card'
import ConfirmDialog from '../../components/ui/ConfirmDialog'
import DropdownMenu from '../../components/ui/DropdownMenu'
import Modal from '../../components/ui/Modal'
import { Table, TBody, TD, TH, THead, TR, TableEmpty } from '../../components/ui/Table'

type UserUpdatePayload = {
  email?: string
  password?: string
  role?: string
  full_name?: string
  active?: boolean
}

const historyLimit = 20

const hasSystemAdminDesignation = (user: User) => !!(user.system_admin_designated || user.installation_operator)

const roleLabel = (user: User) => user.role === 'admin'
  ? hasSystemAdminDesignation(user) ? 'System admin' : 'Company admin'
  : user.role.replace(/_/g, ' ')


const truncate = (value: string | null | undefined, max = 80) => {
  if (!value) return ''
  if (value.length <= max) return value
  return `${value.slice(0, Math.max(0, max - 3))}...`
}

const changeSummary = (entry: AuditLogDetail) => {
  if (!entry.old_value && entry.new_value) return 'Created'
  if (entry.old_value && !entry.new_value) return 'Deleted'
  if (entry.old_value && entry.new_value) {
    const changedKeys = Object.keys(entry.new_value).filter((key) => {
      const oldValue = entry.old_value ? entry.old_value[key] : undefined
      const newValue = entry.new_value ? entry.new_value[key] : undefined
      return JSON.stringify(oldValue) !== JSON.stringify(newValue)
    })
    if (changedKeys.length > 0) {
      return `Updated ${changedKeys.join(', ')}`
    }
  }
  return entry.action
}

export default function UserManagement() {
  const { user: currentUser } = useAuth()
  const toast = useToast()
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<'active' | 'inactive' | 'all'>('active')
  const pageSize = 20
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [pendingDeleteUser, setPendingDeleteUser] = useState<User | null>(null)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['users', page, search, status],
    queryFn: async () => {
      const activeFilter = status === 'all' ? '' : `&active=${status === 'active'}`
      const response = await api.get<PaginatedResponse<User>>(`/users?skip=${page * pageSize}&limit=${pageSize}&q=${encodeURIComponent(search.trim())}${activeFilter}`)
      return response.data
    },
  })

  useEffect(() => {
    if (data && page > 0 && page * pageSize >= data.total) { setPage(Math.max(0, Math.ceil(data.total / pageSize) - 1)); return }
    if (!data?.items.length) {
      setSelectedUserId(null)
      return
    }
    if (!selectedUserId || !data.items.some((user) => user.id === selectedUserId)) {
      setSelectedUserId(data.items[0].id)
    }
  }, [data, selectedUserId, page])

  const selectedUser = useMemo(
    () => data?.items.find((user) => user.id === selectedUserId) ?? null,
    [data, selectedUserId]
  )

  const loginHistory = useQuery({
    queryKey: ['user-logins', selectedUserId],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<LoginHistoryEntry>>(
        `/users/${selectedUserId}/logins?limit=${historyLimit}`
      )
      return response.data
    },
    enabled: !!selectedUserId,
  })

  const editHistory = useQuery({
    queryKey: ['user-edits', selectedUserId],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<AuditLogDetail>>(
        `/users/${selectedUserId}/edits?limit=${historyLimit}`
      )
      return response.data
    },
    enabled: !!selectedUserId,
  })

  const auditTrail = useQuery({
    queryKey: ['user-audit', selectedUserId],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<AuditLogDetail>>(
        `/users/${selectedUserId}/audit?limit=${historyLimit}`
      )
      return response.data
    },
    enabled: !!selectedUserId,
  })

  const createMutation = useMutation({
    mutationFn: async (payload: { email: string; password: string; role: string; full_name: string }) => {
      await api.post('/users', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowCreateModal(false)
      toast.success('User created')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to create user')
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data: payload }: { id: string; data: UserUpdatePayload }) => {
      await api.put(`/users/${id}`, payload)
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['user-edits', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['user-audit', variables.id] })
      toast.success('User updated')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to update user')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/users/${id}`)
    },
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['user-edits', id] })
      queryClient.invalidateQueries({ queryKey: ['user-audit', id] })
      setPendingDeleteUser(null)
      if (selectedUserId === id) {
        setSelectedUserId(null)
      }
      toast.success('Account deactivated', { description: 'Account deactivated. View inactive users to review its history or reactivate it.' })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Could not deactivate account')
    },
  })

  const handleCreate = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    createMutation.mutate({
      email: formData.get('email') as string,
      password: formData.get('password') as string,
      role: formData.get('role') as string,
      full_name: formData.get('full_name') as string,
    })
  }

  const handleUpdate = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!editingUser) return
    const formData = new FormData(e.currentTarget)
    const payload: UserUpdatePayload = {
      full_name: formData.get('full_name') as string,
      email: formData.get('email') as string,
      role: formData.get('role') as string,
      active: (formData.get('active') as string) === 'true',
    }
    const password = formData.get('password') as string
    if (password) {
      payload.password = password
    }
    updateMutation.mutate(
      { id: editingUser.id, data: payload },
      {
        onSuccess: () => {
          setEditingUser(null)
        },
      }
    )
  }

  const roleTone = (role: string) => {
    if (role === 'admin') return 'red'
    if (role === 'manager') return 'amber'
    if (role === 'approver') return 'purple'
    if (role === 'assigned_reviewer') return 'teal'
    return 'blue'
  }

  const buildUserMenuItems = (user: User, isSelf: boolean) => {
    const systemAccountRestricted = hasSystemAdminDesignation(user) && !currentUser?.installation_operator
    const items: Array<{
      key: string
      label: string
      onSelect: () => void
      disabled?: boolean
      tone?: 'default' | 'destructive'
    }> = [
      { key: 'edit', label: 'Edit', disabled: systemAccountRestricted, onSelect: () => setEditingUser(user) },
      user.active ? {
        key: 'deactivate', label: 'Deactivate account', tone: 'destructive',
        disabled: isSelf || systemAccountRestricted,
        onSelect: () => setPendingDeleteUser(user),
      } : {
        key: 'reactivate', label: 'Reactivate account', disabled: isSelf || systemAccountRestricted,
        onSelect: () => updateMutation.mutate({ id: user.id, data: { active: true } }),
      },
    ]
    return items
  }

  const users = data?.items || []

  return (
    <div className="workflow-page users-page min-w-0 space-y-4">
      <header className="py-1">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-ink">User Management</h1>
            <p className="mt-1 text-sm text-muted">Create, edit, and review user activity.</p>
          </div>
          <Button variant="primary" onClick={() => setShowCreateModal(true)}>
            Create user
          </Button>
        </div>
      </header>

      <div className="workflow-toolbar flex flex-wrap items-end justify-between gap-3">
        <div className="w-full sm:max-w-sm"><label htmlFor="user-search" className="mb-1 block text-sm font-medium">Find a colleague</label><input id="user-search" type="search" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0) }} placeholder="Search by name or email" className="w-full px-3 py-2" /></div>
        <div className="w-full sm:w-auto">
          <label htmlFor="user-status" className="mb-1 block text-sm font-medium">Show users</label>
          <select id="user-status" value={status} onChange={(event) => {
            setStatus(event.target.value as typeof status)
            setPage(0)
            setSelectedUserId(null)
          }} className="w-full px-3 py-2">
            <option value="active">Active users</option>
            <option value="inactive">Inactive users</option>
            <option value="all">All users</option>
          </select>
        </div>
        <p role="status" className="text-sm text-muted">{isFetching ? 'Loading users…' : isError ? '' : `${data?.total ?? 0} ${data?.total === 1 ? 'user' : 'users'}${search ? ' match your search' : ''}`}</p>
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          {isError ? <LoadError subject="Users" onRetry={() => refetch()} /> : isLoading ? (
            <Card className="p-6 text-sm text-muted">Loading...</Card>
          ) : (
            <Card className="overflow-hidden"><div className="workflow-table-heading"><h2>People and permissions</h2><p>Select a colleague to review their access and activity.</p></div>
              <div data-testid="users-mobile-cards" className="divide-y divide-line lg:hidden">
                {users.map((user) => {
                  const isSelected = user.id === selectedUserId
                  const isSelf = currentUser?.id === user.id
                  return (
                    <div
                      key={user.id}
                      className={`cursor-pointer p-4 hover:bg-canvas ${
                        isSelected ? 'bg-info-soft' : ''
                      }`}
                      onClick={() => setSelectedUserId(user.id)}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <button type="button" className="text-left text-sm font-semibold text-accent break-words hover:underline" aria-pressed={isSelected} onClick={() => setSelectedUserId(user.id)}>{user.full_name}</button>
                          <p className="text-xs text-muted break-all">{user.email}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <Badge tone={roleTone(user.role)}>{roleLabel(user)}</Badge>
                            <Badge tone={user.active ? 'green' : 'slate'}>
                              {user.active ? 'Active' : 'Inactive'}
                            </Badge>
                            <Badge tone="slate">Created {formatDate(user.created_at)}</Badge>
                          </div>
                        </div>
                        <DropdownMenu
                          ariaLabel={`Actions for ${user.full_name}`}
                          items={buildUserMenuItems(user, !!isSelf)}
                        />
                      </div>
                    </div>
                  )
                })}
                {users.length === 0 ? (
                  <div className="p-6 text-center text-sm text-muted">No users found.</div>
                ) : null}
              </div>

              <div className="hidden overflow-x-auto lg:block">
                <Table>
                  <THead>
                    <tr>
                      <TH>Name & email</TH>
                      <TH>Role</TH>
                      <TH>Status</TH>
                      <TH className="w-[1%]">Actions</TH>
                    </tr>
                  </THead>
                  <TBody>
                    {users.map((user) => {
                      const isSelected = user.id === selectedUserId
                      const isSelf = currentUser?.id === user.id
                      return (
                        <TR
                          key={user.id}
                          className={`cursor-pointer ${isSelected ? 'bg-info-soft' : ''}`}
                          onClick={() => setSelectedUserId(user.id)}
                        >
                          <TD className="text-ink break-words min-w-[200px]"><button type="button" className="text-left font-semibold text-accent hover:underline" aria-pressed={isSelected} onClick={() => setSelectedUserId(user.id)}>{user.full_name}</button><p className="mt-1 text-xs text-muted break-all">{user.email}</p></TD>
                          <TD>
                            <Badge tone={roleTone(user.role)}>{roleLabel(user)}</Badge>
                          </TD>
                          <TD>
                            <Badge tone={user.active ? 'green' : 'slate'}>
                              {user.active ? 'Active' : 'Inactive'}
                            </Badge>
                          </TD>
                          <TD className="text-right" onClick={(e) => e.stopPropagation()}>
                            <DropdownMenu
                              ariaLabel={`Actions for ${user.full_name}`}
                              items={buildUserMenuItems(user, !!isSelf)}
                            />
                          </TD>
                        </TR>
                      )
                    })}
                    {users.length === 0 ? <TableEmpty colSpan={4}>No users found.</TableEmpty> : null}
                  </TBody>
                </Table>
              </div>
            </Card>
          )}
          {!isError && (data?.total || 0) > pageSize && <nav aria-label="User pages" className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <span className="text-sm text-muted">{page * pageSize + 1}–{Math.min((page + 1) * pageSize, data?.total || 0)} of {data?.total}</span>
            <div className="flex gap-2"><Button disabled={page === 0 || isFetching} onClick={() => setPage((value) => value - 1)}>Previous page</Button><Button disabled={(page + 1) * pageSize >= (data?.total || 0) || isFetching} onClick={() => setPage((value) => value + 1)}>Next page</Button></div>
          </nav>}
        </div>

        <div className="xl:col-span-1">
          <Card className="p-4 xl:sticky xl:top-20">
            {selectedUser ? (
              <div className="space-y-6">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">

                    <div className="mt-1 text-lg font-semibold text-ink break-words">
                      {selectedUser.full_name}
                    </div>
                    <div className="text-sm text-muted break-all">{selectedUser.email}</div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Badge tone={roleTone(selectedUser.role)}>{roleLabel(selectedUser)}</Badge>
                      <Badge tone={selectedUser.active ? 'green' : 'slate'}>
                        {selectedUser.active ? 'Active' : 'Inactive'}
                      </Badge>
                      <Badge tone="slate">Created {formatDate(selectedUser.created_at)}</Badge>
                    </div>
                  </div>
                  <DropdownMenu
                    ariaLabel={`Actions for ${selectedUser.full_name}`}
                    items={buildUserMenuItems(selectedUser, currentUser?.id === selectedUser.id)}
                  />
                </div>

                {hasSystemAdminDesignation(selectedUser) && !selectedUser.installation_operator && (
                  <p className="text-sm text-muted">This account retains its system admin designation. System admin access requires an active account with the Company admin role.</p>
                )}
                {hasSystemAdminDesignation(selectedUser) && !currentUser?.installation_operator && (
                  <p className="text-sm text-muted">Only a system admin can change this account.</p>
                )}

                <div className="space-y-4">
                  <details className="border-t border-line py-3">
                    <summary className="cursor-pointer text-sm font-semibold">
                      <span>Login History</span>
                      <span className="ml-2 text-xs font-normal text-muted">{loginHistory.isError ? 'Unavailable' : `Latest ${Math.min(historyLimit, loginHistory.data?.total || 0)} of ${loginHistory.data?.total || 0}`}</span>
                    </summary>
                    {loginHistory.isError ? <LoadError subject="Login history" onRetry={() => loginHistory.refetch()} /> : loginHistory.isLoading ? (
                      <div className="mt-2 text-xs text-muted">Loading...</div>
                    ) : loginHistory.data?.items.length ? (
                      <div className="mt-3 space-y-2 max-h-48 overflow-y-auto">
                        {loginHistory.data.items.map((entry) => (
                          <div key={entry.id} className="text-xs text-ink">
                            <div className="font-medium text-ink">
                              {formatDateTime(entry.timestamp)}
                            </div>
                            <div className="text-muted">
                              {entry.ip_address || 'Unknown IP'}
                              {entry.user_agent ? ` · ${truncate(entry.user_agent, 60)}` : ''}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-muted">No login activity yet.</div>
                    )}
                  </details>

                  <details className="border-t border-line py-3">
                    <summary className="cursor-pointer text-sm font-semibold">
                      <span>Edit History</span>
                      <span className="ml-2 text-xs font-normal text-muted">{editHistory.isError ? 'Unavailable' : `Latest ${Math.min(historyLimit, editHistory.data?.total || 0)} of ${editHistory.data?.total || 0}`}</span>
                    </summary>
                    {editHistory.isError ? <LoadError subject="Edit history" onRetry={() => editHistory.refetch()} /> : editHistory.isLoading ? (
                      <div className="mt-2 text-xs text-muted">Loading...</div>
                    ) : editHistory.data?.items.length ? (
                      <div className="mt-3 space-y-2 max-h-48 overflow-y-auto">
                        {editHistory.data.items.map((entry) => (
                          <div key={entry.id} className="text-xs text-ink">
                            <div className="font-medium text-ink">{changeSummary(entry)}</div>
                            <div className="text-muted">{formatDateTime(entry.timestamp)}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-muted">No edits recorded.</div>
                    )}
                  </details>

                  <details className="border-t border-line py-3">
                    <summary className="cursor-pointer text-sm font-semibold">
                      <span>Audit Trail</span>
                      <span className="ml-2 text-xs font-normal text-muted">{auditTrail.isError ? 'Unavailable' : `Latest ${Math.min(historyLimit, auditTrail.data?.total || 0)} of ${auditTrail.data?.total || 0}`}</span>
                    </summary>
                    {auditTrail.isError ? <LoadError subject="Audit trail" onRetry={() => auditTrail.refetch()} /> : auditTrail.isLoading ? (
                      <div className="mt-2 text-xs text-muted">Loading...</div>
                    ) : auditTrail.data?.items.length ? (
                      <div className="mt-3 space-y-2 max-h-48 overflow-y-auto">
                        {auditTrail.data.items.map((entry) => (
                          <div key={entry.id} className="text-xs text-ink">
                            <div className="font-medium text-ink">
                              {entry.action} {entry.entity_type}
                            </div>
                            <div className="text-muted">
                              {truncate(entry.entity_id, 24)} · {formatDateTime(entry.timestamp)}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-muted">No audit activity yet.</div>
                    )}
                  </details>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted">Select a user to see details.</div>
            )}
          </Card>
        </div>
      </div>

      <Modal
        open={showCreateModal}
        title="Create user"
        onClose={() => setShowCreateModal(false)}
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="usermanagement-field-1" className="text-sm font-medium text-ink">Full name</label>
            <input id="usermanagement-field-1"
              type="text"
              name="full_name"
              required
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="usermanagement-field-2" className="text-sm font-medium text-ink">Email</label>
            <input id="usermanagement-field-2"
              type="email"
              name="email"
              required
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="usermanagement-field-3" className="text-sm font-medium text-ink">Password</label>
            <input id="usermanagement-field-3"
              type="password"
              name="password"
              required
              minLength={8}
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="usermanagement-field-4" className="text-sm font-medium text-ink">Role</label>
            <select id="usermanagement-field-4"
              name="role"
              required
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            >
              <option value="contributor">Contributor</option>
              <option value="approver">Approver</option>
              <option value="manager">Manager</option>
              <option value="assigned_reviewer">Assigned Reviewer</option>
              <option value="admin">Company admin</option>
            </select>
          </div>
          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button variant="secondary" type="button" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" loading={createMutation.isPending}>
              Create
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!editingUser}
        title="Edit user"
        onClose={() => setEditingUser(null)}
      >
        {editingUser ? (
          <form onSubmit={handleUpdate} className="space-y-4">
            <div className="flex flex-col gap-1">
              <label htmlFor="usermanagement-field-5" className="text-sm font-medium text-ink">Full name</label>
              <input id="usermanagement-field-5"
                type="text"
                name="full_name"
                defaultValue={editingUser.full_name}
                required
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="usermanagement-field-6" className="text-sm font-medium text-ink">Email</label>
              <input id="usermanagement-field-6"
                type="email"
                name="email"
                defaultValue={editingUser.email}
                required
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <label htmlFor="usermanagement-field-7" className="text-sm font-medium text-ink">Role</label>
                <select id="usermanagement-field-7"
                  name="role"
                  defaultValue={editingUser.role}
                  required
                  className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                >
                  <option value="contributor">Contributor</option>
                  <option value="approver">Approver</option>
                  <option value="manager">Manager</option>
                  <option value="assigned_reviewer">Assigned Reviewer</option>
                  <option value="admin">Company admin</option>
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="usermanagement-field-8" className="text-sm font-medium text-ink">Status</label>
                <select id="usermanagement-field-8"
                  name="active"
                  defaultValue={editingUser.active ? 'true' : 'false'}
                  required
                  className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                >
                  <option value="true">Active</option>
                  <option value="false">Inactive</option>
                </select>
              </div>
            </div>
            {hasSystemAdminDesignation(editingUser) && (
              <p className="text-sm text-muted">This account's system admin designation is managed separately and cannot be granted or removed here. System admin access requires an active account with the Company admin role.</p>
            )}
            <div className="flex flex-col gap-1">
              <label htmlFor="usermanagement-field-9" className="text-sm font-medium text-ink">Reset password (optional)</label>
              <input id="usermanagement-field-9"
                type="password"
                name="password"
                minLength={8}
                placeholder="Leave blank to keep current password"
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
            </div>
            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <Button variant="secondary" type="button" onClick={() => setEditingUser(null)}>
                Cancel
              </Button>
              <Button variant="primary" type="submit" loading={updateMutation.isPending}>
                Save changes
              </Button>
            </div>
          </form>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={!!pendingDeleteUser}
        title="Deactivate account?"
        description={
          pendingDeleteUser
            ? `Deactivate ${pendingDeleteUser.full_name}? This removes the account from active users and prevents sign-in. Its history is preserved; you can find or reactivate it under Inactive users.`
            : ''
        }
        confirmLabel="Deactivate account"
        dangerDetails={['Remove from active users and prevent sign-in', 'Retain the account and audit history under Inactive users']}
        onClose={() => setPendingDeleteUser(null)}
        onConfirm={() => {
          if (!pendingDeleteUser) return
          deleteMutation.mutate(pendingDeleteUser.id)
        }}
        isWorking={deleteMutation.isPending}
      />
    </div>
  )
}
