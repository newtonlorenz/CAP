import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
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
import useProductTour from './useProductTour'
import { getProductTour } from './productTourCatalog'
import ProductTourInvitation from './ProductTourInvitation'
import './productTour.css'

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
  label: 'Overview',
  aliases: ['Dashboard'],
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
  const { user, sessionError, isLoading: isAuthLoading } = useAuth()
  const { jurisdictionId, jurisdictions, isLoading: isJurisdictionLoading, error: jurisdictionError, retry: retryJurisdictions, setJurisdictionId } = useJurisdiction()
  const { brand } = useSiteContent()
  const location = useLocation()
  const [resourcesOpen, setResourcesOpen] = useState(false)
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false)
  const definition = useMemo(() => getProductTour(location.pathname, location.search, location.hash), [location.pathname, location.search, location.hash])
  const tour = useProductTour({
    tour: definition,
    userId: user?.id, ready: !!user && !isAuthLoading,
    routeKey: `${location.pathname}${location.search}${location.hash}`,
    prepare: () => setIsMobileNavOpen(false),
  })
  const isResourcesVisible = tour.isRunning
    ? definition.steps.some(step => step.target?.includes('primary-nav')) && window.innerWidth >= 1280
    : resourcesOpen
  const resourcesRef = useRef<HTMLDivElement>(null)
  const resourcesTrigger = useRef<HTMLButtonElement>(null)
  const mobileDrawerRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const coreItems = [dashboardItem, licenceApplicationsItem, certificationProjectsItem, changeManagementItem]
  const secondarySections: NavSection[] = [
    { id: 'resources', label: 'Resources', items: resourceItems },
    { id: 'workspace', label: 'Workspace', items: [teamsItem, reportsItem] },
    { id: 'help', label: 'Help', items: [guideItem, changeNotesItem] },
    ...(user?.role === 'admin' ? [{ id: 'admin', label: 'Administration', items: adminItems }] : []),
  ]
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
  const pageItems = primaryNavSections.flatMap(section => section.items.map(item => ({ ...item, section: section.label })))
    .concat(resourceItems.map(item => ({ ...item, section: 'Resources' })))
    .concat(user?.role === 'admin' ? adminItems.map(item => ({ ...item, section: 'Administration' })) : [])
    .concat([{ path: '/account', label: 'My account', section: 'Account', icon: <></> }])
  const currentPage = pageItems.find(itemActive)
  const pageLabel = location.pathname === '/market-setup' ? 'Market setup' : location.pathname.startsWith('/review-cycles/') ? 'Requirement assessment' : currentPage?.label || 'Overview'
  useEffect(() => { document.title = `${pageLabel} · ${brand.name}` }, [pageLabel, brand.name])
  useEffect(() => { setIsMobileNavOpen(false); setResourcesOpen(false) }, [location.pathname, location.search])
  useEffect(() => {
    if (!resourcesOpen || tour.isRunning) return
    const dismiss = (event: PointerEvent) => { if (!resourcesRef.current?.contains(event.target as Node)) setResourcesOpen(false) }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setResourcesOpen(false); resourcesTrigger.current?.focus() }
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', escape) }
  }, [resourcesOpen, tour.isRunning])
  useEffect(() => {
    if (!isMobileNavOpen) return
    const previous = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    const content = contentRef.current
    content?.setAttribute('inert', '')
    document.body.style.overflow = 'hidden'
    const focusable = () => Array.from(mobileDrawerRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), select:not([disabled]), [tabindex="0"]') || [])
    focusable()[0]?.focus()
    const onKey = (event: KeyboardEvent) => {
      // A draft confirmation opened from navigation owns focus until it closes.
      if (document.querySelector('[role="dialog"]:not([aria-label="Navigation"])')) return
      if (event.key === 'Escape') { event.preventDefault(); setIsMobileNavOpen(false) }
      if (event.key !== 'Tab') return
      const items = focusable(), first = items[0], last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    const onResize = () => { if (window.innerWidth >= 1280) setIsMobileNavOpen(false) }
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('keydown', onKey); window.removeEventListener('resize', onResize)
      content?.removeAttribute('inert'); document.body.style.overflow = previousOverflow; previous?.focus()
    }
  }, [isMobileNavOpen])
  const needsJurisdiction = !['/jurisdictions', '/guide', '/change-notes', '/access-teams', '/library'].includes(location.pathname) && !location.pathname.startsWith('/admin/')
  const noJurisdiction = needsJurisdiction && !isJurisdictionLoading && !jurisdictionError && jurisdictions.length === 0
  const jurisdictionSelector = (variant: string) => <div className="cap-market-selector">
    <label className="sr-only" htmlFor={`jurisdiction-${variant}`}>Jurisdiction</label>
    <select id={`jurisdiction-${variant}`} aria-label="Jurisdiction selector" value={jurisdictionId || ''}
      onChange={event => setJurisdictionId(event.target.value)} disabled={isJurisdictionLoading || jurisdictions.length <= 1}>
      {!jurisdictions.length && <option value="">{isJurisdictionLoading ? 'Loading…' : 'No active jurisdictions'}</option>}
      {jurisdictions.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"><path d="m6 9 6 6 6-6" /></svg>
  </div>
  const resourceLink = (item: NavItem) => <Link key={item.path} to={item.path} aria-current={itemActive(item) ? 'page' : undefined}
    data-tour={item === dashboardItem ? 'overview' : item === licenceApplicationsItem ? 'licences' : item === certificationProjectsItem ? 'certifications' : item === changeManagementItem ? 'changes' : item === requirementsItem ? 'requirements' : item === reviewsItem ? 'assessment' : item === evidenceItem ? 'evidence' : item === reportsItem ? 'reports' : undefined}
    className="app-nav-link flex items-center gap-3 px-3 py-2">{item.icon}<span>{item.label}</span></Link>
  const tourEntry = <button type="button" aria-label="Product tour" disabled={tour.isRunning}
    className="app-nav-link flex w-full items-center gap-3 px-3 py-2 text-left" onClick={() => { void tour.start() }}>
    <Icon><circle cx="12" cy="12" r="9" /><path d="m10 8 6 4-6 4z" /></Icon><span>Product tour</span>
  </button>

  return <ToastProvider>
    <div className="app-modern-shell min-h-screen">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <ToastViewport /><ProductFeedback />
      {isMobileNavOpen && <>
        <div className="fixed inset-0 z-40 bg-slate-950/60 xl:hidden" onClick={() => setIsMobileNavOpen(false)} aria-hidden="true" />
        <aside data-testid="mobile-nav-drawer" id="mobile-navigation" ref={mobileDrawerRef} role="dialog" aria-modal="true" aria-label="Navigation" className="cap-mobile-drawer fixed inset-y-0 left-0 z-50 flex w-80 max-w-[90vw] flex-col bg-surface xl:hidden">
          <div className="flex items-center justify-between border-b border-line px-5 py-4"><Brand /><button type="button" onClick={() => setIsMobileNavOpen(false)} className="min-h-11 rounded-md px-3 text-sm text-muted">Close</button></div>
          <div className="border-b border-line px-5 py-3">{jurisdictionSelector('mobile')}</div>
          <nav aria-label="Primary navigation" className="min-h-0 overflow-y-auto p-3">
            {coreItems.map(resourceLink)}
            {secondarySections.map(section => <section key={section.id} className="mt-5"><h2 className="mb-1 px-3 text-xs font-semibold text-muted">{section.label}</h2>{section.items.map(resourceLink)}{section.id === 'help' && tourEntry}</section>)}
            <div className="mt-4 border-t border-line pt-3"><Link to="/account" className="app-nav-link block px-3 py-2">My account</Link></div>
          </nav>
        </aside>
      </>}
      <div ref={contentRef} className="min-w-0">
        <header className="app-topbar">
          <button type="button" data-testid="mobile-nav-toggle" onClick={() => setIsMobileNavOpen(value => !value)} className="cap-mobile-toggle" aria-label="Toggle navigation" aria-expanded={isMobileNavOpen} aria-controls="mobile-navigation"><HamburgerIcon /></button>
          <Link to="/" className="cap-header-brand" aria-label={`${brand.name} overview`}><Brand /></Link>
          <div className="cap-header-market">{jurisdictionSelector('desktop')}</div>
          <nav aria-label="Primary navigation" data-testid="primary-nav" className="cap-primary-nav">
            {coreItems.map(item => <Link key={item.path} to={item.path} data-tour={item === dashboardItem ? 'overview' : item === licenceApplicationsItem ? 'licences' : item === certificationProjectsItem ? 'certifications' : 'changes'} className="cap-primary-link" aria-current={itemActive(item) ? 'page' : undefined}>{item.label}</Link>)}
            <div className="cap-resources" ref={resourcesRef} onBlur={event => { if (!tour.isRunning && !event.currentTarget.contains(event.relatedTarget as Node | null)) setResourcesOpen(false) }}>
              <button ref={resourcesTrigger} data-testid="resources-trigger" type="button" className="cap-primary-link" aria-expanded={isResourcesVisible} aria-controls="resource-navigation" data-active={secondarySections.some(section => section.items.some(itemActive)) || undefined}
                onClick={() => setResourcesOpen(value => !value)} onKeyDown={event => {
                  if (event.key === 'ArrowDown') { event.preventDefault(); setResourcesOpen(true); requestAnimationFrame(() => resourcesRef.current?.querySelector<HTMLAnchorElement>('a')?.focus()) }
                }}>Resources<svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m6 9 6 6 6-6" /></svg></button>
              {isResourcesVisible && <div id="resource-navigation" className="cap-resource-panel" data-testid="nav-resources">
                {secondarySections.map(section => <section key={section.id}><h2>{section.label}</h2>{section.items.map(resourceLink)}{section.id === 'help' && tourEntry}</section>)}
              </div>}
            </div>
          </nav>
          <div className="cap-header-actions"><NavigationSearch items={pageItems} /><div className="cap-profile"><ProfileDropdown /></div></div>
        </header>
        <main id="main-content" tabIndex={-1} className="app-modern-content">
          {tour.showInvitation && <ProductTourInvitation title={definition.title} summary={definition.summary} stepCount={definition.steps.length} interrupted={tour.record?.status === 'interrupted'} onStart={() => { void tour.start(tour.record?.status === 'interrupted') }} onDismiss={tour.dismiss} />}
          {tour.error && <p role="alert" className="mb-4 rounded-lg border border-warning-line bg-warning-soft p-3 text-sm text-warning">{tour.error}</p>}
          {sessionError && <p role="alert" className="mb-4 rounded-md border border-danger-line bg-danger-soft p-3 text-sm text-danger">{sessionError}</p>}
          {jurisdictionError && <p role="alert" className="mb-4 rounded-md border border-warning-line bg-warning-soft p-3 text-sm text-warning">{jurisdictionError} <button type="button" className="underline" onClick={retryJurisdictions}>Retry</button></p>}
          {noJurisdiction && location.pathname !== '/account' ? <section className="cap-empty-state"><h1>Set up a jurisdiction</h1><p>An active jurisdiction is needed to organise requirements, projects and reviews.</p>{user?.role === 'admin' ? <NavLink className="mt-4 inline-block text-sm font-semibold text-accent underline" to="/jurisdictions">Manage jurisdictions</NavLink> : <p>Ask an administrator to activate your jurisdiction.</p>}</section> : <Suspense fallback={<p role="status" className="py-12 text-center text-muted">Loading workspace…</p>}><Outlet /></Suspense>}
        </main>
      </div>
    </div>
  </ToastProvider>
}
