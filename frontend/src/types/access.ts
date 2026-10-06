export type Visibility = 'organisation' | 'restricted' | 'secret'
export type Permission = 'summary' | 'view' | 'edit' | 'approve' | 'export' | 'manage_access'
export type ResourceType = 'application' | 'certification_project' | 'preparation_case' | 'preparation_evidence'
export interface ResourceAccess { visibility: Visibility; permissions: Permission[]; revision: number }
export interface AccessGrant { subject_type: 'user' | 'team'; subject_id: string; permissions: Permission[] }
export interface AccessPolicy { resource_type: ResourceType; resource_id: string; visibility: Visibility; owner_id: string; revision: number; grants: AccessGrant[]; effective_permissions: Permission[]; parent_type?: ResourceType | null; parent_id?: string | null }
export interface AccessTeam { id: string; name: string; owner_id: string; member_ids: string[]; revision: number }
export const visibilityLabels: Record<Visibility, string> = { 'secret': 'Highly confidential', 'restricted': 'Restricted', 'organisation': 'Organisation' }
export const permissionLabels: Record<Permission, string> = { summary: 'Summary only', view: 'View details', edit: 'Edit', approve: 'Approve', export: 'Export', manage_access: 'Manage access' }

export const visibilityDescriptions: Record<Visibility, string> = {
  organisation: 'People in your organisation can access this according to their role.',
  restricted: 'Only you have access initially. Grant access to named people or teams.',
  'secret': 'Only you have access initially. Grant access to named people; team sharing is unavailable.',
}
export const permissionDescriptions: Record<Permission, string> = {
  summary: 'See the application name, stage and deadline without its contents.',
  view: 'Read the contents and supporting information.',
  edit: 'Change drafts. View details is also required; this does not grant approval.',
  approve: 'Approve completed work. View details and an approval role are also required.',
  export: 'Download packs and attachments. View details is also required.',
  manage_access: 'Change visibility and recipients. Account administration does not grant this permission.',
}
