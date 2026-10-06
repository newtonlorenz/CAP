import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { DraftNavigationProvider } from './hooks/useDraftNavigationGuard'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import SiteContentProvider from './contexts/SiteContentProvider'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: 1,
    },
  },
})

const router = createBrowserRouter([{ path: '*', element: <DraftNavigationProvider><App /></DraftNavigationProvider> }], { basename: import.meta.env.BASE_URL })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SiteContentProvider>
        <RouterProvider router={router} />
      </SiteContentProvider>
    </QueryClientProvider>
  </StrictMode>,
)
