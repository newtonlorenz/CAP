import { useEffect, useState, type ReactNode } from 'react'
import { defaultSiteContent, parseSiteContent } from '../config/siteContent'
import { SiteContentContext } from './SiteContentContext'

export default function SiteContentProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState(defaultSiteContent)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${import.meta.env.BASE_URL}site-content.json`, {
      cache: 'no-store',
      credentials: 'omit',
      signal: controller.signal,
    }).then((response) => {
      if (!response.ok) throw new Error(`Site content returned ${response.status}`)
      return response.json()
    }).then((value: unknown) => {
      setContent(parseSiteContent(value))
    }).catch(() => {
      // Keep the neutral built-in content when the optional file is unavailable.
    })
    return () => controller.abort()
  }, [])

  return <SiteContentContext.Provider value={content}>{children}</SiteContentContext.Provider>
}
