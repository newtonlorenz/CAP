import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { JurisdictionProvider } from './contexts/JurisdictionContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import { useTheme } from './hooks/useTheme'
const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Jurisdictions = lazy(() => import('./pages/Jurisdictions'))
const RequirementsList = lazy(() => import('./pages/RequirementsList'))
const RequirementsSetView = lazy(() => import('./pages/RequirementsSetView'))
const RequirementsSetEdit = lazy(() => import('./pages/RequirementsSetEdit'))
const RequirementsSetImport = lazy(() => import('./pages/RequirementsSetImport'))
const RequirementDetail = lazy(() => import('./pages/RequirementDetail'))
const ReviewCycles = lazy(() => import('./pages/ReviewCycles'))
const ReviewCycleDetail = lazy(() => import('./pages/ReviewCycleDetail'))
const Reports = lazy(() => import('./pages/Reports'))
const CertificationProjects = lazy(() => import('./pages/CertificationProjects'))
const Preparation = lazy(() => import('./pages/Preparation'))
const Library = lazy(() => import('./pages/Library'))
const AccessTeams = lazy(() => import('./pages/AccessTeams'))
const Applications = lazy(() => import('./pages/Applications'))
const MarketSetup = lazy(() => import('./pages/MarketSetup'))
const ChangeManagement = lazy(() => import('./pages/ChangeManagement'))
const ProgramWorkspace = lazy(() => import('./pages/ProgramWorkspace'))
const GuideFaq = lazy(() => import('./pages/GuideFaq'))
const ChangeNotes = lazy(() => import('./pages/ChangeNotes'))
const AccountSettings = lazy(() => import('./pages/AccountSettings'))
const Settings = lazy(() => import('./pages/admin/Settings'))
const UserManagement = lazy(() => import('./pages/admin/UserManagement'))
const ProductFeedback = lazy(() => import('./pages/admin/ProductFeedback'))
const NotFound = lazy(() => import('./pages/NotFound'))

function App() {
  // Keep system and cross-tab appearance updates active with the menu closed.
  useTheme()
  return (
    <AuthProvider>
      <JurisdictionProvider>
        <Suspense fallback={<p role="status" className="p-8 text-center">Loading application…</p>}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="jurisdictions" element={<Jurisdictions />} />
              <Route path="requirements" element={<RequirementsList />} />
              <Route path="requirements/sets/:documentId" element={<RequirementsSetView />} />
              <Route
                path="requirements/sets/:documentId/edit"
                element={<RequirementsSetEdit />}
              />
              <Route
                path="requirements/sets/:documentId/import"
                element={<RequirementsSetImport />}
              />
              <Route path="requirements/:id" element={<RequirementDetail />} />
              <Route path="review-cycles" element={<ReviewCycles />} />
              <Route path="certification-projects" element={<CertificationProjects />} />
              <Route path="preparation" element={<Preparation key="preparation" />} />
              <Route path="library" element={<Library />} />
              <Route path="access-teams" element={<AccessTeams />} />
              <Route path="licence-applications" element={<Applications />} />
              <Route element={<ProtectedRoute requiredRole="manager" />}>
                <Route path="market-setup" element={<MarketSetup />} />
              </Route>
              <Route path="change-management" element={<ChangeManagement />} />
              <Route path="program-workspace" element={<ProgramWorkspace />} />
              <Route path="account" element={<AccountSettings />} />
              <Route path="guide" element={<GuideFaq />} />
              <Route path="change-notes" element={<ChangeNotes />} />
              <Route path="review-cycles/:id" element={<ReviewCycleDetail />} />
              <Route path="reports" element={<Reports />} />
              <Route element={<ProtectedRoute requiredRole="admin" />}>
                <Route path="admin/settings" element={<Settings />} />
                <Route path="admin/users" element={<UserManagement />} />
                <Route path="admin/feedback" element={<ProductFeedback />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Route>
          </Route>
        </Routes>
        </Suspense>
      </JurisdictionProvider>
    </AuthProvider>
  )
}

export default App
