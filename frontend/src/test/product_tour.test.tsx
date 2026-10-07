import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Config, Driver } from 'driver.js'
import useProductTour from '../components/useProductTour'
import { productTourKey, readProductTour, writeProductTour } from '../components/productTourState'

const mocked = vi.hoisted(() => ({ config: null as Config | null, index: 0, active: false, omitDestroyed: false, destroy: vi.fn() }))
vi.mock('driver.js', () => ({
  driver: (config: Config) => {
    mocked.config = config
    const hooks = () => ({ config, state: {}, driver: tour as unknown as Driver })
    const highlight = () => config.onHighlightStarted?.(undefined, {}, hooks())
    const tour = {
      drive: (index: number) => { mocked.index = index; mocked.active = true; highlight() },
      destroy: () => { mocked.destroy(); mocked.active = false; if (!mocked.omitDestroyed) config.onDestroyed?.(undefined, {}, hooks()) },
      isActive: () => mocked.active,
      getActiveIndex: () => mocked.index,
      hasNextStep: () => mocked.index < 3,
      moveNext: () => { mocked.index += 1; highlight() },
      movePrevious: () => { mocked.index = Math.max(0, mocked.index - 1); highlight() },
    }
    return tour
  },
}))

function Harness({ userId = 'one', ready = true, routeKey = '/' }: { userId?: string; ready?: boolean; routeKey?: string }) {
  const tour = useProductTour({ userId, ready, routeKey, prepare: () => {} })
  return <>
    {tour.showInvitation && <span>Invitation</span>}
    {tour.isRunning && <span>Running</span>}
    <button onClick={() => { void tour.start() }}>Replay</button>
    <button onClick={() => { void tour.start(true) }}>Resume</button>
    <button onClick={tour.dismiss}>Dismiss</button>
  </>
}

describe('product tour persistence and lifecycle', () => {
  beforeEach(() => {
    localStorage.clear()
    mocked.config = null; mocked.index = 0; mocked.active = false; mocked.omitDestroyed = false; mocked.destroy.mockClear()
    vi.restoreAllMocks()
  })

  it('rejects corrupt, invalid and unknown-version records', () => {
    for (const value of ['{', '{"status":"done","step":0}', '{"status":"interrupted","step":4}', '{"status":"dismissed","step":-1}', '{"status":"interrupted","step":0.5}']) {
      localStorage.setItem(productTourKey('one'), value)
      expect(readProductTour('one')).toBeNull()
    }
    localStorage.setItem('cap:product-tour:v0:one', '{"status":"completed","step":3}')
    localStorage.removeItem(productTourKey('one'))
    expect(readProductTour('one')).toBeNull()
  })

  it('isolates dismissal and completion by user', () => {
    writeProductTour('one', { status: 'dismissed', step: 1 })
    writeProductTour('two', { status: 'completed', step: 3 })
    expect(readProductTour('one')).toEqual({ status: 'dismissed', step: 1 })
    expect(readProductTour('two')).toEqual({ status: 'completed', step: 3 })
    expect(readProductTour('three')).toBeNull()
  })

  it('safely handles unavailable storage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(readProductTour('one')).toBeNull()
    expect(() => writeProductTour('one', { status: 'dismissed', step: 0 })).not.toThrow()
    render(<Harness />)
    fireEvent.click(screen.getByText('Dismiss'))
    expect(screen.queryByText('Invitation')).not.toBeInTheDocument()
  })

  it('does not invite or load Driver before authentication is ready', () => {
    render(<Harness ready={false} />)
    expect(screen.queryByText('Invitation')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Replay'))
    expect(mocked.config).toBeNull()
  })

  it('requires explicit resume, interrupts on navigation, and replays from the start', async () => {
    writeProductTour('one', { status: 'interrupted', step: 2 })
    const view = render(<Harness />)
    expect(screen.getByText('Invitation')).toBeInTheDocument()
    expect(mocked.config).toBeNull()
    fireEvent.click(screen.getByText('Resume'))
    await waitFor(() => expect(mocked.active).toBe(true))
    expect(mocked.index).toBe(2)
    view.rerender(<Harness routeKey="/requirements?view=source" />)
    expect(mocked.destroy).toHaveBeenCalledOnce()
    expect(readProductTour('one')).toEqual({ status: 'interrupted', step: 2 })
    fireEvent.click(screen.getByText('Replay'))
    await waitFor(() => expect(mocked.active).toBe(true))
    expect(mocked.index).toBe(0)
  })

  it('persists keyboard completion separately from Escape dismissal', async () => {
    render(<Harness />)
    fireEvent.click(screen.getByText('Replay'))
    await waitFor(() => expect(mocked.active).toBe(true))
    act(() => { for (let i = 0; i < 4; i += 1) fireEvent.keyDown(document, { key: 'ArrowRight' }) })
    expect(readProductTour('one')).toEqual({ status: 'completed', step: 3 })
    fireEvent.click(screen.getByText('Replay'))
    await waitFor(() => expect(mocked.active).toBe(true))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(readProductTour('one')).toEqual({ status: 'dismissed', step: 0 })
  })

  it('cleans up when Driver omits its destroy hook during an initial animation', async () => {
    mocked.omitDestroyed = true
    render(<Harness />)
    fireEvent.click(screen.getByText('Replay'))
    await waitFor(() => expect(mocked.active).toBe(true))
    fireEvent.keyDown(document, { key: 'ArrowLeft' })
    expect(mocked.active).toBe(true)
    expect(mocked.index).toBe(0)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(mocked.active).toBe(false)
    expect(screen.queryByText('Running')).not.toBeInTheDocument()
    expect(readProductTour('one')).toEqual({ status: 'dismissed', step: 0 })
  })

  it('removes active overlay and listeners on identity change and unmount', async () => {
    const view = render(<Harness />)
    fireEvent.click(screen.getByText('Replay'))
    await waitFor(() => expect(mocked.active).toBe(true))
    view.rerender(<Harness userId="two" />)
    expect(mocked.active).toBe(false)
    expect(readProductTour('two')).toBeNull()
    fireEvent.click(screen.getByText('Replay'))
    await waitFor(() => expect(mocked.active).toBe(true))
    view.unmount()
    expect(mocked.active).toBe(false)
    expect(mocked.destroy).toHaveBeenCalledTimes(2)
  })

  it('cancels a pending lazy launch on navigation', async () => {
    const view = render(<Harness />)
    fireEvent.click(screen.getByText('Replay'))
    view.rerender(<Harness routeKey="/reports" />)
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 40)) })
    expect(mocked.active).toBe(false)
    expect(screen.queryByText('Running')).not.toBeInTheDocument()
    expect(readProductTour('one')).toEqual({ status: 'interrupted', step: 0 })
  })
})
