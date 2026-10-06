import { describe, it, expect, beforeEach } from 'vitest'
import api, {
  applyCsrfHeader,
  normalizeFormDataHeaders,
  shouldRedirectOnUnauthorized,
} from '../api/client'
import { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { getApiErrorDetail, getApiErrorMessage } from '../api/errors'

describe('API Client', () => {
  beforeEach(() => {
    document.cookie = 'csrf_token=; Max-Age=0; path=/'
  })

  it('should have the correct base URL', () => {
    expect(api.defaults.baseURL).toBe('/api/v1')
  })

  it('should send cookies with requests', () => {
    expect(api.defaults.withCredentials).toBe(true)
  })

  it('should add CSRF header for unsafe methods', async () => {
    const config = applyCsrfHeader(
      { method: 'post', headers: {} } as unknown as InternalAxiosRequestConfig,
      'csrf_token=test-csrf-token; path=/'
    )
    const headers =
      config.headers instanceof AxiosHeaders ? config.headers : new AxiosHeaders(config.headers)
    expect(headers.get('X-CSRF-Token')).toBe('test-csrf-token')
  })

  it('should not add CSRF header for safe methods', async () => {
    const config = applyCsrfHeader(
      { method: 'get', headers: {} } as unknown as InternalAxiosRequestConfig,
      'csrf_token=test-csrf-token; path=/'
    )
    const headers =
      config.headers instanceof AxiosHeaders ? config.headers : new AxiosHeaders(config.headers)
    expect(headers.get('X-CSRF-Token')).toBeUndefined()
  })

  it('should drop JSON content type for FormData payloads', () => {
    const formData = new FormData()
    formData.append('file', new File(['backup'], 'backup.capbak'))

    const config = normalizeFormDataHeaders({
      method: 'post',
      data: formData,
      headers: { 'Content-Type': 'application/json' },
    } as unknown as InternalAxiosRequestConfig)

    const headers =
      config.headers instanceof AxiosHeaders ? config.headers : new AxiosHeaders(config.headers)
    expect(headers.get('Content-Type')).toBeUndefined()
  })

  it('should keep content type for non-FormData payloads', () => {
    const config = normalizeFormDataHeaders({
      method: 'post',
      data: { ok: true },
      headers: { 'Content-Type': 'application/json' },
    } as unknown as InternalAxiosRequestConfig)

    const headers =
      config.headers instanceof AxiosHeaders ? config.headers : new AxiosHeaders(config.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  describe('401 redirect behavior', () => {
    it('should not redirect on 401 from /users/me', async () => {
      expect(shouldRedirectOnUnauthorized('/users/me', '/requirements')).toBe(false)
    })

    it('should not redirect on 401 from /auth/me', async () => {
      expect(shouldRedirectOnUnauthorized('/auth/me', '/requirements')).toBe(false)
    })

    it('should not redirect on 401 from /auth/login', async () => {
      expect(shouldRedirectOnUnauthorized('/auth/login', '/requirements')).toBe(false)
    })

    it('should not redirect on 401 while already on /login', async () => {
      expect(shouldRedirectOnUnauthorized('/requirements', '/login')).toBe(false)
    })

    it('should redirect on 401 from protected endpoints', async () => {
      expect(shouldRedirectOnUnauthorized('/requirements', '/requirements')).toBe(true)
    })
  })

  describe('API error details', () => {
    it('should format FastAPI validation detail arrays', () => {
      const error = {
        isAxiosError: true,
        response: {
          status: 422,
          data: {
            detail: [{ loc: ['body', 'file'], msg: 'Field required', type: 'missing' }],
          },
        },
      }

      expect(getApiErrorDetail(error)).toBe('file: Field required')
      expect(getApiErrorMessage(error, 'Failed to import backup')).toBe('file: Field required')
    })
  })
})
