import { createContext, useContext } from 'react'
import { defaultSiteContent, type SiteContent } from '../config/siteContent'

export const SiteContentContext = createContext<SiteContent>(defaultSiteContent)

export function useSiteContent(): SiteContent {
  return useContext(SiteContentContext)
}
