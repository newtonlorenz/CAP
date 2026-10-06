import { useState } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, Link, Outlet, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { DraftNavigationProvider, useDraftNavigationGuard } from '../hooks/useDraftNavigationGuard'

function Editor() {
  const [value, setValue] = useState('')
  const [saved, setSaved] = useState(false)
  useDraftNavigationGuard(Boolean(value) && !saved)
  return <><label>Draft answer<input value={value} onChange={(event) => { setValue(event.target.value); setSaved(false) }} /></label><Link to="/other">Another page</Link><button onClick={() => setSaved(true)}>Complete pending save</button></>
}

function setup() {
  const router = createMemoryRouter([{ path: '/', element: <DraftNavigationProvider><Outlet /></DraftNavigationProvider>, children: [
    { path: 'edit', element: <Editor /> }, { path: 'other', element: <h1>Other page</h1> },
  ] }], { basename: '/cap', initialEntries: ['/cap/other', '/cap/edit'], initialIndex: 1 })
  render(<RouterProvider router={router} />)
  fireEvent.change(screen.getByLabelText('Draft answer'), { target: { value: 'Unsaved company details' } })
  return router
}

describe('shared draft navigation', () => {
  it('keeps draft edits when cancelling a route change, then continues once saved', async () => {
    const router = setup()
    expect(screen.getByRole('link', { name: 'Another page' })).toHaveAttribute('href', '/cap/other')
    fireEvent.click(screen.getByRole('link', { name: 'Another page' }))
    expect(await screen.findByRole('dialog', { name: 'Changes are not saved yet' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByLabelText('Draft answer')).toHaveValue('Unsaved company details')
    expect(router.state.location.pathname).toBe('/cap/edit')
    fireEvent.click(screen.getByRole('link', { name: 'Another page' }))
    await screen.findByRole('dialog')
    // The pending network save can settle while navigation is blocked.
    fireEvent.click(screen.getByRole('button', { name: 'Complete pending save', hidden: true }))
    expect(await screen.findByRole('heading', { name: 'Other page' })).toBeVisible()
    expect(router.state.location.pathname).toBe('/cap/other')
    router.dispose()
  })

  it('blocks browser Back and warns on unload until leaving is explicitly chosen', async () => {
    const router = setup()
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
    await act(async () => { await router.navigate(-1) })
    await screen.findByRole('dialog', { name: 'Changes are not saved yet' })
    expect(router.state.location.pathname).toBe('/cap/edit')
    fireEvent.click(screen.getByRole('button', { name: 'Leave with unsaved changes' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/cap/other'))
    const afterLeaving = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(afterLeaving)
    expect(afterLeaving.defaultPrevented).toBe(false)
    router.dispose()
  })
})
