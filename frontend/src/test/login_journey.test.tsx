import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import Login from '../pages/Login'
import ProtectedRoute from '../components/ProtectedRoute'
const { login } = vi.hoisted(() => ({ login: vi.fn() }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ login, isAuthenticated: false, isLoading: false, user: null }) }))
function Destination() { const location = useLocation(); return <p>Destination: {location.pathname}{location.search}</p> }
function setup(from = '/review-cycles/123?mode=focus&item=a') {
  return render(<MemoryRouter initialEntries={[{ pathname: '/login', state: { from } }]}><Routes><Route path="/login" element={<Login />} /><Route path="*" element={<Destination />} /></Routes></MemoryRouter>)
}
async function submit() {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'person@example.test' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
}
beforeEach(() => { login.mockReset(); login.mockResolvedValue(undefined) })
describe('Sign-in journey', () => {
  it('returns to the requested review and preserves its filters', async () => {
    setup(); await submit()
    expect(await screen.findByText('Destination: /review-cycles/123?mode=focus&item=a')).toBeInTheDocument()
    expect(login).toHaveBeenCalledWith('person@example.test', 'test-password')
  })
  it.each(['https://example.test', '//example.test'])('rejects an external return destination %s', async (from) => {
    setup(from); await submit()
    expect(await screen.findByText('Destination: /')).toBeInTheDocument()
  })
  it('shows and hides the entered password without changing it', () => {
    setup()
    const field = screen.getByLabelText('Password')
    fireEvent.change(field, { target: { value: 'test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(field).toHaveAttribute('type', 'text'); expect(field).toHaveValue('test-password')
    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(field).toHaveAttribute('type', 'password')
  })
  it('keeps the form available with a recovery message after a connection failure', async () => {
    login.mockRejectedValue(new Error('Offline')); setup(); await submit()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Check your connection and try again'))
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeEnabled()
  })
  it('remembers the full destination when an unauthenticated user opens a protected page', () => {
    function Notice() { return <p>Return to: {useLocation().state?.from}</p> }
    render(<MemoryRouter initialEntries={['/reviews/123?pending=1']}><Routes><Route element={<ProtectedRoute />}><Route path="/reviews/:id" element={<p>Private</p>} /></Route><Route path="/login" element={<Notice />} /></Routes></MemoryRouter>)
    expect(screen.getByText('Return to: /reviews/123?pending=1')).toBeInTheDocument()
    expect(screen.queryByText('Private')).not.toBeInTheDocument()
  })
})
