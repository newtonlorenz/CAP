import { useCallback, useEffect, useRef, useState } from 'react'
import type { Driver, DriveStep } from 'driver.js'
import { readProductTour, writeProductTour, type ProductTourRecord } from './productTourState'

const steps = [
  { target: 'requirements', title: 'Find a requirement', path: 'Resources → Requirements', description: 'Browse the source requirements before you start an assessment. Open a requirement to read its details.' },
  { target: 'assessment', title: 'Understand assessment work', path: 'Resources → Assessment overview', description: 'Open an assessment to review each requirement, record findings, and track decisions with your team.' },
  { target: 'evidence', title: 'Locate supporting evidence', path: 'Resources → Evidence', description: 'Browse reusable evidence in the library. In an assessment, attach the evidence that supports each finding.' },
  { target: 'reports', title: 'Check progress and reports', path: 'Workspace → Reports', description: 'Review assessment progress and reports. Use Help → Product tour to repeat this tour at any time.' },
]

function tourSteps(mobile: boolean): DriveStep[] {
  return steps.map(step => ({
    // A missing or hidden target uses Driver's floating popover. No record is required.
    element: mobile ? undefined : () => {
      const target = document.querySelector<HTMLElement>(`[data-testid="primary-nav"] [data-tour="${step.target}"]`)
      if (target?.getClientRects().length && getComputedStyle(target).visibility !== 'hidden' && !target.closest('[inert]')) return target
      // Driver accepts an unresolved element at runtime and creates its floating target.
      return document.getElementById('driver-dummy-element')!
    },
    popover: {
      title: step.title,
      description: `${step.description}<p class="cap-tour-path">${mobile ? 'Open Navigation → ' : step.target === 'reports' ? 'Resources → ' : ''}${step.path}</p>`,
      side: 'bottom', align: 'start',
    },
  }))
}

export default function useProductTour({ userId, ready, routeKey, prepare }: {
  userId: string | undefined
  ready: boolean
  routeKey: string
  prepare: () => void
}) {
  const [record, setRecord] = useState<ProductTourRecord | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [invitationSafe, setInvitationSafe] = useState(false)
  const driverRef = useRef<Driver | null>(null)
  const generation = useRef(0)
  const prepareRef = useRef(prepare)
  prepareRef.current = prepare
  const stopRef = useRef<(() => void) | null>(null)
  const recordRef = useRef<{ userId: string; value: ProductTourRecord | null } | null>(null)

  useEffect(() => {
    if (userId && recordRef.current?.userId !== userId) {
      recordRef.current = { userId, value: readProductTour(userId) }
      setRecord(recordRef.current.value)
    }
    setError(null)
    return () => {
      generation.current += 1
      stopRef.current?.()
      stopRef.current = null
    }
  }, [userId, ready, routeKey])

  useEffect(() => {
    const check = () => {
      const focus = document.activeElement
      setInvitationSafe(!document.querySelector('[role="dialog"], [aria-modal="true"]') &&
        !(focus instanceof HTMLElement && focus.matches('input, textarea, select, [contenteditable="true"]')))
    }
    check()
    const observer = new MutationObserver(check)
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['role', 'aria-modal'] })
    document.addEventListener('focusin', check)
    document.addEventListener('focusout', check)
    return () => { observer.disconnect(); document.removeEventListener('focusin', check); document.removeEventListener('focusout', check) }
  }, [])

  const save = useCallback((value: ProductTourRecord) => {
    if (!userId) return
    recordRef.current = { userId, value }
    writeProductTour(userId, value)
    setRecord(value)
  }, [userId])

  const start = useCallback(async (resume = false) => {
    if (!ready || !userId || isRunning) return
    const launch = ++generation.current
    const mobile = window.innerWidth < 1280
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    let currentStep = resume ? recordRef.current?.value?.step || 0 : 0
    let ending: ProductTourRecord['status'] = 'dismissed'
    let finished = false
    let viewportWidth = window.innerWidth
    const finish = () => {
      if (finished) return
      finished = true
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
      if (window.innerWidth !== viewportWidth) { viewportWidth = window.innerWidth; interrupt() }
    }
    const next = () => {
      const active = driverRef.current
      if (!active) return
      if (active.hasNextStep()) active.moveNext()
      else { ending = 'completed'; active.destroy(); finish() }
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
        else if (event.key === 'ArrowLeft') { if ((active.getActiveIndex() || 0) > 0) active.movePrevious() }
        else {
          // Driver includes the highlighted link in its default Tab order.
          // Keep keyboard focus on the tour controls to protect the current task.
          const controls = Array.from(document.querySelectorAll<HTMLButtonElement>('.cap-product-tour button:not([disabled])'))
            .filter(button => button.style.display !== 'none')
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
      const tour = driver({
        steps: tourSteps(mobile), animate: !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
        smoothScroll: false, allowClose: true, overlayClickBehavior: close,
        disableActiveInteraction: true, allowKeyboardControl: false,
        popoverClass: 'cap-product-tour', showProgress: true,
        progressText: 'Step {{current}} of {{total}}', showButtons: ['previous', 'next', 'close'],
        nextBtnText: 'Next', prevBtnText: 'Back', doneBtnText: 'Finish',
        onPopoverRender: popover => {
          popover.closeButton.setAttribute('aria-label', 'Close product tour')
          popover.wrapper.setAttribute('aria-modal', 'true')
          popover.progress.setAttribute('aria-live', 'polite')
        },
        onHighlightStarted: (element, _step, { driver: active }) => {
          // Driver checks the window bounds, but a resource link can still be
          // clipped by a scrollable navigation container.
          element?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'auto' })
          currentStep = active.getActiveIndex() || 0
          save({ status: 'interrupted', step: currentStep })
        },
        onNextClick: next,
        onCloseClick: close,
        onDestroyed: finish,
      })
      driverRef.current = tour
      tour.drive(currentStep)
    } catch {
      if (launch !== generation.current || finished) return
      ending = 'interrupted'
      driverRef.current?.destroy()
      finish()
      setError('The product tour could not start. Try again from Help → Product tour.')
    }
  }, [ready, userId, isRunning, save])

  return {
    isRunning, error, record,
    showInvitation: ready && !!userId && !isRunning && invitationSafe && (!record || record.status === 'interrupted'),
    start,
    dismiss: () => save({ status: 'dismissed', step: record?.step || 0 }),
  }
}
