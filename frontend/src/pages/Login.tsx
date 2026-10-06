import { useState, FormEvent } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import axios from 'axios'
import Brand from '../components/Brand'
import ThemeSwitcher from '../components/ThemeSwitcher'
import Button from '../components/ui/Button'
import { useSiteContent } from '../contexts/SiteContentContext'

export default function Login() {
  const [searchParams] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [capsLock, setCapsLock] = useState(false)
  const location = useLocation()
  const [isLoading, setIsLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()
  const restoredNotice = searchParams.get('restored') === '1'
  const { brand, login: content } = useSiteContent()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      await login(email, password)
      const from = location.state?.from
      navigate(typeof from === 'string' && from.startsWith('/') && !from.startsWith('//') ? from : '/', { replace: true })
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined
      if (status === 401) {
        setError('Invalid email or password')
      } else if (status) {
        setError('Sign-in is temporarily unavailable. Please try again.')
      } else {
        setError('Unable to connect. Check your connection and try again.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="login-page">
      <header className="login-header"><Brand /><ThemeSwitcher /></header>
      <main className="login-main">
        <section className="login-intro" aria-label="About this workspace">
          <h1>{content.heading}</h1>
          <p>{content.description}</p>
          {content.information.length > 0 && <div className="login-workflow">
            {content.information.map((item) => <div key={item.title}><strong>{item.title}</strong><span>{item.description}</span></div>)}
          </div>}
        </section>
        <section className="login-panel" aria-labelledby="sign-in-title">
          <h2 id="sign-in-title">{content.formHeading}</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{content.formDescription}</p>
          {restoredNotice && <div className="mt-5 rounded-lg border border-brand-line bg-brand-soft p-3 text-sm text-accent">Restore completed. Sign in with an admin account from the restored system.</div>}
          <form onSubmit={handleSubmit}>
            {error && <div role="alert" className="mb-5 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger">{error}</div>}
            <div className="mb-5">
              <label htmlFor="email" className="mb-2 block text-sm font-semibold text-ink">Email</label>
              <input id="email" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false}
                value={email} onChange={(event) => setEmail(event.target.value)}
                className="w-full px-3 py-2.5 text-sm" placeholder="you@company.com" required />
            </div>
            <div className="mb-6">
              <label htmlFor="password" className="mb-2 block text-sm font-semibold text-ink">Password</label>
              <div className="relative">
                <input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password"
                  value={password} onChange={(event) => setPassword(event.target.value)}
                  onKeyUp={(event) => setCapsLock(event.getModifierState('CapsLock'))} onBlur={() => setCapsLock(false)}
                  className="w-full py-2.5 pl-3 pr-16 text-sm" required />
                <button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}
                  onClick={() => setShowPassword((value) => !value)} className="absolute inset-y-1 right-1 rounded-md px-3 text-xs font-semibold text-muted hover:bg-subtle">
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              {capsLock && <p role="status" className="mt-2 text-xs text-warning">Caps Lock is on.</p>}
            </div>
            <Button type="submit" variant="primary" disabled={isLoading} className="min-h-11 w-full">{isLoading ? 'Signing in…' : 'Sign In'}</Button>
          </form>
          <p className="mt-6 text-center text-xs leading-relaxed text-muted">{content.accessHelp}</p>
        </section>
      </main>
      <footer className="login-footer"><span>{brand.name}</span><span>{content.footer}</span></footer>
    </div>
  )
}
