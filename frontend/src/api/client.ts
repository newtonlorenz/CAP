import axios, { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'

const SAFE_METHODS = new Set(['get', 'head', 'options'])
export const NO_REDIRECT_401_PATHS = ['/auth/login', '/auth/logout', '/auth/refresh', '/users/me', '/auth/me']

export function getCookieValue(cookieString: string, name: string): string | null {
  const prefix = `${name}=`
  const parts = cookieString.split(';')
  for (const rawPart of parts) {
    const part = rawPart.trim()
    if (part.startsWith(prefix)) {
      return decodeURIComponent(part.substring(prefix.length))
    }
  }
  return null
}

export function shouldRedirectOnUnauthorized(
  requestUrl: string,
  currentPathname: string
): boolean {
  if (currentPathname === `${import.meta.env.BASE_URL}login`) {
    return false
  }
  return !NO_REDIRECT_401_PATHS.some((path) => requestUrl.includes(path))
}

export function applyCsrfHeader(
  config: InternalAxiosRequestConfig,
  cookieString: string
): InternalAxiosRequestConfig {
  const method = (config.method || 'get').toLowerCase()
  if (SAFE_METHODS.has(method)) {
    return config
  }

  const csrfToken = getCookieValue(cookieString, 'csrf_token')
  if (!csrfToken) {
    return config
  }

  const headers =
    config.headers instanceof AxiosHeaders ? config.headers : new AxiosHeaders(config.headers)
  headers.set('X-CSRF-Token', csrfToken)
  config.headers = headers
  return config
}

export function normalizeFormDataHeaders(
  config: InternalAxiosRequestConfig
): InternalAxiosRequestConfig {
  if (typeof FormData === 'undefined' || !(config.data instanceof FormData)) {
    return config
  }

  const headers =
    config.headers instanceof AxiosHeaders ? config.headers : new AxiosHeaders(config.headers)
  headers.delete('Content-Type')
  config.headers = headers
  return config
}

const api = axios.create({
  baseURL: `${import.meta.env.BASE_URL}api/v1`,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const normalizedConfig = normalizeFormDataHeaders(config)
  return applyCsrfHeader(normalizedConfig, document.cookie)
})

let refreshInFlight: Promise<unknown> | null = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const requestUrl = typeof error.config?.url === 'string' ? error.config.url : ''
    if (error.response?.status === 401 && error.config && !error.config._renewed &&
        !['/auth/login', '/auth/logout', '/auth/refresh'].some(path => requestUrl.includes(path))) {
      error.config._renewed = true
      try {
        if (!refreshInFlight) refreshInFlight = api.post('/auth/refresh').finally(() => { refreshInFlight = null })
        await refreshInFlight
        return api.request(error.config)
      } catch { /* Preserve the original request error and normal session-expiry handling. */ }
    }
    if (
      error.response?.status === 401 &&
      shouldRedirectOnUnauthorized(requestUrl, window.location.pathname)
    ) {
      window.location.href = `${import.meta.env.BASE_URL}login`
    }
    return Promise.reject(error)
  }
)

export default api
