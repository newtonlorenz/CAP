import { useCallback, useEffect, useRef, useState } from 'react'
import type { Driver, DriveStep } from 'driver.js'
import { PRODUCT_OVERVIEW_TOUR, type ProductTourDefinition } from './productTourCatalog'
import { productTourKey, readProductTour, writeProductTour, type ProductTourRecord } from './productTourState'

// Driver renders popover strings as HTML. Catalog text stays literal.
function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!)
}

const mobilePaths: Record<string, string> = {
  overview: 'Overview', licences: 'Licence Applications', certifications: 'Certifications', changes: 'Change Management',
  requirements: 'Resources → Requirements', assessment: 'Resources → Assessment overview',
  evidence: 'Resources → Evidence', reports: 'Workspace → Reports',
}

function stepDescription(step: ProductTourDefinition['steps'][number], mobile: boolean) {
  const path = mobile && step.target?.includes('primary-nav')
    ? mobilePaths[step.target.match(/data-tour="([^"\n]+)"/)?.[1] || ''] : undefined
  return escapeHtml(step.description) + (path ? `<p class="cap-tour-path">${escapeHtml(`Navigation → ${path}`)}</p>` : '')
}

function tourSteps(tour: ProductTourDefinition, mobile: boolean): DriveStep[] {
  return tour.steps.map(step => ({
    element: !step.target || (mobile && step.target.includes('primary-nav')) ? undefined : () => {
      const targets = document.querySelectorAll<HTMLElement>(step.target!)
      const target = Array.from(targets).find(element => element.getClientRects().length &&
        getComputedStyle(element).visibility !== 'hidden' && !element.closest('[inert], [hidden]'))
      // Driver uses a floating popover for an unresolved target.
      return target || document.getElementById('driver-dummy-element')!
    },
    popover: {
      title: escapeHtml(step.title),
      description: stepDescription(step, mobile),
      side: 'bottom', align: 'start',
    },
  }))
}

export default function useProductTour({ userId, ready, routeKey, prepare, tour = PRODUCT_OVERVIEW_TOUR }: {
  userId: string | undefined
  tour?: ProductTourDefinition
  ready: boolean
  routeKey: string
  prepare: () => void
}) {
  const [stored, setStored] = useState<{ key: string; value: ProductTourRecord | null } | null>(null)
  const key = productTourKey(userId || '', tour.id)
  const record = stored?.key === key ? stored.value : null
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [invitationSafe, setInvitationSafe] = useState(false)
  const driverRef = useRef<Driver | null>(null)
  const generation = useRef(0)
  const prepareRef = useRef(prepare)
  prepareRef.current = prepare
  const stopRef = useRef<(() => void) | null>(null)
  const sessionRecords = useRef(new Map<string, ProductTourRecord | null>())

  useEffect(() => {
    if (userId) {
      if (!sessionRecords.current.has(key)) sessionRecords.current.set(key, readProductTour(userId, tour))
      setStored({ key, value: sessionRecords.current.get(key) || null })
    } else setStored(null)
    setError(null)
    return () => {
      generation.current += 1
      stopRef.current?.()
      stopRef.current = null
    }
  }, [userId, ready, routeKey, key, tour])

  useEffect(() => {
    const focus = document.activeElement
    // Snapshot eligibility at a route/session boundary. Toggling the banner
    // during pointer focus moves controls between mousedown and mouseup.
    setInvitationSafe(ready && !document.querySelector('[role="dialog"], [aria-modal="true"]') &&
      !(focus instanceof HTMLElement && focus.matches('input, textarea, select, [contenteditable="true"]')))
  }, [ready, userId, routeKey])

  const save = useCallback((value: ProductTourRecord) => {
    if (!userId) return
    sessionRecords.current.set(key, value)
    writeProductTour(userId, value, tour.id)
    setStored({ key, value })
  }, [userId, key, tour.id])

  const start = useCallback(async (resume = false) => {
    if (!ready || !userId || isRunning || stopRef.current || document.querySelector('[role="dialog"]:not([aria-label="Navigation"]), [aria-modal="true"]:not([aria-label="Navigation"])')) return
    const launch = ++generation.current
    const mobile = window.innerWidth < 1280
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    let currentStep = resume ? sessionRecords.current.get(key)?.step || 0 : 0
    let ending: ProductTourRecord['status'] = 'dismissed'
    let finished = false
    let transitioning = false
    let queuedDirection: -1 | 0 | 1 = 0
    let controls: { nextButton: HTMLButtonElement; previousButton: HTMLButtonElement } | null = null
    const updateControls = () => {
      if (!controls) return
      controls.nextButton.disabled = transitioning
      controls.previousButton.disabled = transitioning || currentStep === 0
      controls.nextButton.classList.toggle('driver-popover-btn-disabled', transitioning)
      controls.previousButton.classList.toggle('driver-popover-btn-disabled', transitioning || currentStep === 0)
    }
    let viewportWidth = window.innerWidth
    let viewportHeight = window.innerHeight
    const finish = () => {
      if (finished) return
      finished = true
      queuedDirection = 0
      controls = null
      window.removeEventListener('resize', onResize)
      document.removeEventListener('keydown', onKey, true)
      driverRef.current = null
      stopRef.current = null
      save({ status: ending, step: currentStep })
      setIsRunning(false)
      queueMicrotask(() => {
        const focus = previousFocus?.isConnected && !previousFocus.closest('[inert]') &&
          !(window.innerWidth < 1280 && previousFocus.closest('[data-testid="primary-nav"]'))
          ? previousFocus : document.querySelector<HTMLElement>(window.innerWidth < 1280 ? '[data-testid="mobile-nav-toggle"]' : '[data-testid="resources-trigger"]')
        focus?.focus({ preventScroll: true })
      })
    }
    const interrupt = () => {
      generation.current += 1
      ending = 'interrupted'
      currentStep = driverRef.current?.getActiveIndex() ?? currentStep
      driverRef.current?.destroy()
      finish()
    }
    const onResize = () => {
      // Driver's positioning becomes stale while its target changes visibility or size.
      if (window.innerWidth !== viewportWidth || window.innerHeight !== viewportHeight) {
        viewportWidth = window.innerWidth; viewportHeight = window.innerHeight; interrupt()
      }
    }
    const next = () => {
      const active = driverRef.current
      if (!active || finished) return
      if (transitioning) { queuedDirection = 1; return }
      if (active.hasNextStep()) active.moveNext()
      else { ending = 'completed'; active.destroy(); finish() }
    }
    const previous = () => {
      const active = driverRef.current
      if (!active || finished) return
      if (transitioning) { queuedDirection = -1; return }
      if ((active.getActiveIndex() || 0) > 0) active.movePrevious()
    }
    const close = () => {
      currentStep = driverRef.current?.getActiveIndex() ?? currentStep
      driverRef.current?.destroy()
      // Driver 1.4.0 omits onDestroyed during its initial animation.
      finish()
    }
    const onKey = (event: KeyboardEvent) => {
      const active = driverRef.current
      if (!active?.isActive()) return
      if (['Escape', 'ArrowRight', 'ArrowLeft', 'Tab'].includes(event.key)) {
        event.preventDefault()
        event.stopImmediatePropagation()
        if (event.key === 'Escape') close()
        else if (event.key === 'ArrowRight') next()
        else if (event.key === 'ArrowLeft') previous()
        else {
          // Driver includes the highlighted link in its default Tab order.
          // Keep keyboard focus on the tour controls to protect the current task.
          const controls = Array.from(document.querySelectorAll<HTMLButtonElement>('.cap-product-tour button:not([disabled])'))
            .filter(button => getComputedStyle(button).display !== 'none' && getComputedStyle(button).visibility !== 'hidden')
          const index = controls.indexOf(document.activeElement as HTMLButtonElement)
          const target = event.shiftKey ? (index <= 0 ? controls.length - 1 : index - 1) : (index + 1) % controls.length
          controls[target]?.focus()
        }
      }
    }
    stopRef.current = interrupt
    window.addEventListener('resize', onResize)
    document.addEventListener('keydown', onKey, true)
    setError(null)
    setIsRunning(true)
    save({ status: 'interrupted', step: currentStep })
    prepareRef.current()
    try {
      const [{ driver }] = await Promise.all([import('driver.js'), import('driver.js/dist/driver.css')])
      if (launch !== generation.current || finished) return
      // React commits the temporary navigation expansion before selectors are resolved.
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
      if (launch !== generation.current || finished) return
      const activeTour = driver({
        steps: tourSteps(tour, mobile), animate: !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
        smoothScroll: false, allowClose: true, overlayClickBehavior: close,
        disableActiveInteraction: true, allowKeyboardControl: false,
        popoverClass: 'cap-product-tour', showProgress: true,
        progressText: 'Step {{current}} of {{total}}', showButtons: ['previous', 'next', 'close'],
        nextBtnText: 'Next', prevBtnText: 'Back', doneBtnText: 'Finish',
        onPopoverRender: popover => {
          controls = popover
          updateControls()
          popover.closeButton.setAttribute('aria-label', 'Close product tour')
          popover.wrapper.setAttribute('aria-modal', 'true')
          popover.progress.setAttribute('aria-live', 'polite')
        },
        onHighlightStarted: (element, _step, { driver: active }) => {
          transitioning = true
          // Driver checks the window bounds, but a resource link can still be
          // clipped by a scrollable navigation container.
          element?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'auto' })
          currentStep = active.getActiveIndex() || 0
          updateControls()
          save({ status: 'interrupted', step: currentStep })
        },
        onHighlighted: () => {
          transitioning = false
          updateControls()
          const direction = queuedDirection
          queuedDirection = 0
          // Driver commits its previous target after this hook returns, even
          // without animation. Flush one requested move after that commit.
          if (direction) queueMicrotask(() => { if (!finished) { if (direction > 0) next(); else previous() } })
        },
        onNextClick: next,
        onPrevClick: previous,
        onCloseClick: close,
        onDestroyed: finish,
      })
      driverRef.current = activeTour
      activeTour.drive(currentStep)
    } catch {
      if (launch !== generation.current || finished) return
      ending = 'interrupted'
      driverRef.current?.destroy()
      finish()
      setError('The product tour could not start. Try again from Help → Product tour.')
    }
  }, [ready, userId, isRunning, save, key, tour])

  return {
    isRunning, error, record,
    showInvitation: ready && !!userId && !isRunning && invitationSafe && (!record || record.status === 'interrupted'),
    start,
    dismiss: () => save({ status: 'dismissed', step: record?.step || 0 }),
  }
}
