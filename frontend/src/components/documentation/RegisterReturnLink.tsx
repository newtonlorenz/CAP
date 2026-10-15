import { Link, useSearchParams } from 'react-router-dom'
import { safeRegisterReturn } from './processNavigation'

export default function RegisterReturnLink() {
  const [params] = useSearchParams()
  const returnTo = safeRegisterReturn(params.get('return_register'))
  return returnTo ? <Link className="mb-3 inline-block text-sm font-semibold text-accent underline" to={returnTo}>Back to documentation register</Link> : null
}
