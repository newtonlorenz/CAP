import { Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { ToastProvider } from '../contexts/ToastContext'
import Brand from './Brand'
import ProfileDropdown from './ProfileDropdown'
import NavigationSearch from './NavigationSearch'
import ToastViewport from './ToastViewport'
import ProductFeedback from './ProductFeedback'
import { useSiteContent } from '../contexts/SiteContentContext'
import Tooltip from './ui/Tooltip'

const DESKTOP_SIDEBAR_COLLAPSED_KEY = 'cap:desktopSidebarCollapsed'

type NavItem = {
  path: string
  label: string
  icon: ReactNode
  aliases?: string[]
}

type NavSection = {
  id: string
  label: string
  items: NavItem[]
}

const Icon = ({ children }: { children: ReactNode }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-6 w-6 shrink-0"
    aria-hidden="true"
    focusable="false"
  >
    {children}
  </svg>
)

const HamburgerIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="h-6 w-6"
    aria-hidden="true"
  >
    <path d="M4 6h16" />
    <path d="M4 12h16" />
    <path d="M4 18h16" />
  </svg>
)

const dashboardItem: NavItem = {
  path: '/',
  label: 'Dashboard',
  icon: (
    <Icon>
      <path d="M3 10.5L12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
      <path d="M9 21v-6h6v6" />
    </Icon>
  ),
}

const programWorkspaceItem: NavItem = {
  path: '/program-workspace',
  label: 'Certification overview',
  aliases: ['Program Workspace'],
  icon: (
    <Icon>
      <path d="M4 6h7v5H4z" />
      <path d="M13 6h7v5h-7z" />
      <path d="M4 13h7v5H4z" />
      <path d="M13 13h7v5h-7z" />
    </Icon>
  ),
}

const requirementsItem: NavItem = {
  path: '/requirements',
  label: 'Requirements',
  icon: (
    <Icon>
      <path d="M9 6h11" />
      <path d="M9 12h11" />
      <path d="M9 18h11" />
      <path d="M4 6h.01" />
      <path d="M4 12h.01" />
      <path d="M4 18h.01" />
    </Icon>
  ),
}

const certificationProjectsItem: NavItem = {
  path: '/certification-projects',
  label: 'Certifications',
  aliases: ['Certification Projects', 'Compliance Certification'],
  icon: (
    <Icon>
      <path d="M4 4h16v16H4z" />
      <path d="M8 8h8" />
      <path d="M8 12h8" />
      <path d="M8 16h5" />
    </Icon>
  ),
}

const licenceApplicationsItem: NavItem = {
  path: '/licence-applications',
  label: 'Licence Applications',
  icon: (
    <Icon>
      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
      <path d="M14 3v6h6M8 13h8M8 17h5" />
    </Icon>
  ),
}

const changeManagementItem: NavItem = {
  path: '/change-management',
  label: 'Change Management',
  icon: (
    <Icon>
      <path d="M12 3v4" />
      <path d="M12 17v4" />
      <path d="M4.9 4.9l2.8 2.8" />
      <path d="M16.3 16.3l2.8 2.8" />
      <path d="M3 12h4" />
      <path d="M17 12h4" />
      <path d="M4.9 19.1l2.8-2.8" />
      <path d="M16.3 7.7l2.8-2.8" />
      <circle cx="12" cy="12" r="3" />
    </Icon>
  ),
}

const reviewsItem: NavItem = {
  path: '/review-cycles',
  label: 'Assessment overview',
  aliases: ['Reviews', 'Review cycles', 'Requirement assessments'],
  icon: (
    <Icon>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 3v6h-6" />
    </Icon>
  ),
}

const reportsItem: NavItem = {
  path: '/reports',
  label: 'Reports',
  icon: (
    <Icon>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 15v-4" />
      <path d="M12 15V7" />
      <path d="M16 15v-6" />
    </Icon>
  ),
}

const jurisdictionsItem: NavItem = {
  path: '/jurisdictions',
  label: 'Jurisdictions',
  icon: (
    <Icon>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a15 15 0 0 1 0 18" />
      <path d="M12 3a15 15 0 0 0 0 18" />
    </Icon>
  ),
}

const guideItem: NavItem = {
  path: '/guide',
  label: 'Guide & FAQ',
  icon: (
    <Icon>
      <path d="M5 4h14v16H5z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
      <path d="M9 16h4" />
    </Icon>
  ),
}

const changeNotesItem: NavItem = {
  path: '/change-notes',
  label: 'Change notes',
  aliases: ['Release notes', "What's new", 'Versions', 'Changelog'],
  icon: (
    <Icon>
      <path d="M5 3h10l4 4v14H5zM15 3v4h4M8 11h8M8 15h8M8 18h5" />
    </Icon>
  ),
}

const formTemplatesItem: NavItem = { path: '/library?section=templates', label: 'Form templates', aliases: ['Templates', 'Preparation templates'], icon: <Icon><path d="M5 3h10l4 4v14H5zM9 11h6M9 15h6" /></Icon> }
const evidenceItem: NavItem = { path: '/library?section=evidence', label: 'Evidence', aliases: ['Evidence library'], icon: <Icon><path d="M3 7h6l2 2h10v11H3zM3 7V4h6l2 3" /></Icon> }
const formsItem: NavItem = { path: '/library?section=forms', label: 'Existing forms', aliases: ['Preparation', 'Forms', 'Standalone forms'], icon: <Icon><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" /></Icon> }
const teamsItem: NavItem = { path: '/access-teams', label: 'Teams', aliases: ['Access teams', 'Team membership'], icon: <Icon><circle cx="9" cy="7" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3" /></Icon> }
const primaryNavSections: NavSection[] = [
  { id: 'overview', label: 'Overview', items: [dashboardItem] },
  { id: 'work', label: 'Work', items: [licenceApplicationsItem, certificationProjectsItem, changeManagementItem] },
  { id: 'workspace', label: 'Workspace', items: [teamsItem] },
  { id: 'reporting', label: 'Reporting', items: [reportsItem] },
  { id: 'help', label: 'Help', items: [guideItem, changeNotesItem] },
]
const resourceItems: NavItem[] = [requirementsItem, formTemplatesItem, evidenceItem, formsItem, programWorkspaceItem, reviewsItem]

const adminItems: NavItem[] = [
  {
    path: '/admin/feedback', label: 'Product feedback',
    icon: <Icon><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H5l-3 2V11.5A8.5 8.5 0 0 1 10.5 3h2a8.5 8.5 0 0 1 8.5 8.5Z" /><path d="M7 10h8M7 14h5" /></Icon>,
  },
  {
    path: '/admin/settings',
    label: 'Settings',
    icon: (
      <Icon>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </Icon>
    ),
  },
  jurisdictionsItem,
  {
    path: '/admin/users',
    label: 'User Management',
    icon: (
      <Icon>
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.85" />
        <path d="M16 3.2a4 4 0 0 1 0 7.6" />
      </Icon>
    ),
  },
]

export default function Layout() {
  const { user, sessionError } = useAuth()
  const {
    jurisdictionId,
    jurisdictions,
    isLoading: isJurisdictionLoading,
    error: jurisdictionError,
    retry: retryJurisdictions,
    setJurisdictionId,
  } = useJurisdiction()
  const location = useLocation()
  const [resourcesExpanded, setResourcesExpanded] = useState<boolean | null>(() => { try { const stored = localStorage.getItem('cap:resourcesExpanded'); return stored === null ? null : stored === 'true' } catch { return null } })
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false)
  const mobileDrawerRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isMobileNavOpen) return
    const previous = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    const content = contentRef.current
    const desktop = document.querySelector<HTMLElement>('[data-testid="desktop-sidebar"]')
    content?.setAttribute('inert', '')
    desktop?.setAttribute('inert', '')
    document.body.style.overflow = 'hidden'
    const focusable = () => Array.from(mobileDrawerRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), select:not([disabled]), [tabindex="0"]'
    ) || [])
    focusable()[0]?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setIsMobileNavOpen(false)
      }
      if (event.key !== 'Tab') return
      const items = focusable()
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first?.focus()
      }
    }
    const onResize = () => {
      if (window.innerWidth >= 1024) setIsMobileNavOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onResize)
      content?.removeAttribute('inert')
      desktop?.removeAttribute('inert')
      document.body.style.overflow = previousOverflow
      previous?.focus()
    }
  }, [isMobileNavOpen])
  const [isDesktopSidebarCollapsed, setIsDesktopSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    try { return window.localStorage.getItem(DESKTOP_SIDEBAR_COLLAPSED_KEY) === '1' } catch { return false }
  })

  const linkClass = ({ collapsed }: { isActive: boolean; collapsed: boolean }) =>
    `app-nav-link group flex w-full items-center ${collapsed ? 'justify-center px-2' : 'gap-3 px-3'} py-2`

  const requestedLibrarySection = new URLSearchParams(location.search).get('section')
  const librarySection = ['requirements', 'templates', 'evidence', 'forms'].includes(requestedLibrarySection || '') ? requestedLibrarySection : 'templates'
  const itemActive = (item: NavItem) => {
    const [path, search] = item.path.split('?')
    if (item.path === formsItem.path && location.pathname === '/preparation') return true
    if (item.path === requirementsItem.path && location.pathname === '/library' && librarySection === 'requirements') return true
    const pathMatches = location.pathname === path || (path !== '/' && location.pathname.startsWith(path + '/'))
    if (!pathMatches || !search) return pathMatches
    return Array.from(new URLSearchParams(search)).every(([key, value]) =>
      (key === 'section' ? librarySection : new URLSearchParams(location.search).get(key)) === value)
  }
  const renderNavLink = (item: NavItem, collapsed: boolean) => (
    <Tooltip key={item.path} content={collapsed ? item.label : undefined}><Link
      to={item.path}
      aria-current={itemActive(item) ? 'page' : undefined}
      aria-label={item.label}
      className={linkClass({ isActive: itemActive(item), collapsed })}
    >
      {item.icon}
      {collapsed ? null : <span className="truncate">{item.label}</span>}
    </Link></Tooltip>
  )

  const renderNav = ({
    collapsed,
    includeAdmin,
  }: {
    collapsed: boolean
    includeAdmin: boolean
  }) => (
    <div className="min-h-0 flex-1 overflow-y-auto pb-6">
      <nav
        aria-label="Primary navigation"
        data-testid="primary-nav"
        className="flex flex-col gap-1 px-2"
      >
        {primaryNavSections.map((section, index) => (
          <div
            key={section.id}
            data-testid={`nav-section-${section.id}`}
            className={index === 0 ? undefined : 'mt-5'}
          >
            {collapsed ? null : (
              <div className="app-nav-section mb-2 px-3">
                {section.label}
              </div>
            )}
            <div className="flex flex-col gap-1">
              {section.items.map((item) => renderNavLink(item, collapsed))}
            </div>
          </div>
        ))}
        <details open={resourcesExpanded ?? resourceItems.some(itemActive)} className="mt-5 px-3" data-testid="nav-resources">
          <summary className="app-nav-section cursor-pointer" onClick={event => {
            event.preventDefault()
            const open = !(resourcesExpanded ?? resourceItems.some(itemActive))
            setResourcesExpanded(open)
            try { localStorage.setItem('cap:resourcesExpanded', String(open)) } catch { /* Keep navigation usable without storage. */ }
          }}>Resources</summary>
          <div className="mt-2 flex flex-col gap-1">{resourceItems.map((item) => renderNavLink(item, collapsed))}</div>
        </details>
        {includeAdmin && user?.role === 'admin' && (
          <>
            <div className="mb-1 mt-5" aria-hidden={collapsed ? 'true' : undefined}>
              {collapsed ? null : (
                <div className="app-nav-section mb-2 px-3">
                  Admin
                </div>
              )}
            </div>
            {adminItems.map((item) => renderNavLink(item, collapsed))}
          </>
        )}
      </nav>
    </div>
  )

  useEffect(() => {
    setIsMobileNavOpen(false)
  }, [location.pathname, location.search])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try { window.localStorage.setItem(
      DESKTOP_SIDEBAR_COLLAPSED_KEY,
      isDesktopSidebarCollapsed ? '1' : '0',
    ) } catch { /* Navigation remains usable when storage is blocked. */ }
  }, [isDesktopSidebarCollapsed])

  const pageItems = primaryNavSections.flatMap((section) => section.items.map((item) => ({ ...item, section: section.label })))
    .concat(resourceItems.map((item) => ({ ...item, section: 'Resources' })))
    .concat(user?.role === 'admin' ? adminItems.map((item) => ({ ...item, section: 'Admin' })) : [])
  const currentPage = pageItems.find(itemActive)
  const pageLabel = location.pathname === '/market-setup' ? 'Market setup' : location.pathname.startsWith('/review-cycles/') ? 'Requirement assessment' : location.pathname === '/account' ? 'My account' : currentPage?.label || 'Overview'
  const { brand } = useSiteContent()
  useEffect(() => { document.title = `${pageLabel} · ${brand.name}` }, [pageLabel, brand.name])
  const needsJurisdiction = !['/jurisdictions', '/guide', '/change-notes', '/access-teams', '/library'].includes(location.pathname) && !location.pathname.startsWith('/admin/')
  const noJurisdiction = needsJurisdiction && !isJurisdictionLoading && !jurisdictionError && jurisdictions.length === 0
  const jurisdictionSelector = (variant: string) => (
    <div className="mx-3 mb-5 rounded-lg border border-line bg-canvas px-3 py-2.5">
      <label className="mb-1 block text-[10px] font-semibold text-muted" htmlFor={`jurisdiction-${variant}`}>Jurisdiction</label>
      <div className="relative">
        <select id={`jurisdiction-${variant}`} aria-label="Jurisdiction selector"
          value={jurisdictionId || ''} onChange={(event) => setJurisdictionId(event.target.value)}
          disabled={isJurisdictionLoading || jurisdictions.length <= 1}
          className="min-h-9 w-full appearance-none border border-line-strong bg-surface py-1.5 pl-2.5 pr-8 text-xs font-semibold text-ink disabled:opacity-100">
          {!jurisdictions.length && <option value="">{isJurisdictionLoading ? 'Loading…' : 'No active jurisdictions'}</option>}
          {jurisdictions.map((item) => <option className="bg-surface text-ink" key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        <svg aria-hidden="true" className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"><path d="m6 9 6 6 6-6" /></svg>
      </div>
    </div>
  )

  return (
    <ToastProvider>
      <div className="app-modern-shell min-h-screen">
        <a href="#main-content" className="skip-link">Skip to content</a>
        <ToastViewport />
        <ProductFeedback />
        <div className="flex min-h-screen">
          <aside data-testid="desktop-sidebar" className={`app-sidebar hidden shrink-0 lg:flex lg:flex-col ${isDesktopSidebarCollapsed ? 'w-16' : 'w-60'}`}>
            <div className={`flex min-h-20 items-center gap-2 ${isDesktopSidebarCollapsed ? 'justify-center px-2' : 'justify-between px-5'}`}>
              {!isDesktopSidebarCollapsed && <Brand />}
              <Tooltip content={isDesktopSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}><button type="button" onClick={() => setIsDesktopSidebarCollapsed((value) => !value)}
                className="shrink-0 rounded-md p-1.5 text-muted hover:bg-subtle hover:text-ink"
                aria-label={isDesktopSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}><HamburgerIcon /></button></Tooltip>
            </div>
            {!isDesktopSidebarCollapsed && jurisdictionSelector('desktop')}
            {renderNav({ collapsed: isDesktopSidebarCollapsed, includeAdmin: true })}
            {!isDesktopSidebarCollapsed && <div className="mx-5 border-t border-line py-4 text-[11px] text-muted">Internal compliance workspace</div>}
          </aside>
          {isMobileNavOpen && <>
            <div className="fixed inset-0 z-40 bg-slate-950/60 lg:hidden" onClick={() => setIsMobileNavOpen(false)} aria-hidden="true" />
            <aside data-testid="mobile-nav-drawer" id="mobile-navigation" ref={mobileDrawerRef}
              role="dialog" aria-modal="true" aria-label="Navigation"
              className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r border-line bg-surface lg:hidden">
              <div className="flex items-center justify-between px-5 py-6"><Brand />
                <button type="button" onClick={() => setIsMobileNavOpen(false)} className="rounded-md border border-line px-2 py-1.5 text-xs text-muted">Close</button>
              </div>
              {jurisdictionSelector('mobile')}
              {renderNav({ collapsed: false, includeAdmin: true })}
            </aside>
          </>}
          <div ref={contentRef} className="min-w-0 flex-1">
            <header className="app-topbar flex items-center justify-between gap-3 px-4 sm:px-7">
              <div className="flex min-w-0 items-center gap-3">
                <button type="button" data-testid="mobile-nav-toggle" onClick={() => setIsMobileNavOpen((value) => !value)}
                  className="rounded-md p-2 text-muted hover:bg-subtle lg:hidden" aria-label="Toggle navigation"
                  aria-expanded={isMobileNavOpen} aria-controls="mobile-navigation"><HamburgerIcon /></button>
                <div className="hidden items-center gap-2 text-xs sm:flex"><span className="text-faint">Workspace</span><span className="text-line-strong" aria-hidden="true">/</span><span className="font-semibold text-ink">{pageLabel}</span></div>
                <span className="truncate text-xs font-semibold text-ink sm:hidden">{pageLabel}</span>
              </div>
              <div className="flex shrink-0 items-center gap-3 sm:gap-5">
                <div className="hidden xl:block"><NavigationSearch items={pageItems} /></div>
                <ProfileDropdown />
              </div>
            </header>
            <main id="main-content" tabIndex={-1} className="app-modern-content p-4 sm:p-7">
              {sessionError && <p role="alert" className="mb-4 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger">{sessionError}</p>}
              {jurisdictionError && <p role="alert" className="mb-4 rounded-lg border border-warning-line bg-warning-soft p-3 text-sm text-warning">{jurisdictionError} <button type="button" className="underline" onClick={retryJurisdictions}>Retry</button></p>}
              {noJurisdiction && location.pathname !== '/account' ? <section className="rounded-xl border border-line bg-surface p-6"><h1 className="text-2xl font-semibold">Set up a jurisdiction</h1><p className="mt-3 text-sm text-muted">An active jurisdiction is needed to organise requirements, projects and reviews.</p>{user?.role === 'admin' ? <NavLink className="mt-4 inline-block text-sm font-semibold text-accent underline" to="/jurisdictions">Manage jurisdictions</NavLink> : <p className="mt-3 text-sm text-muted">Ask an administrator to activate your jurisdiction.</p>}</section> : <Suspense fallback={<p role="status" className="py-12 text-center text-muted">Loading workspace…</p>}><Outlet /></Suspense>}
            </main>
          </div>
        </div>
      </div>
    </ToastProvider>
  )
}
