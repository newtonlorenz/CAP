import { useState } from 'react'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { useDraftNavigationGuard } from './useDraftNavigationGuard'

/** Protect local dialog dismissal as well as workspace navigation. */
export function useLocalDraftGuard(dirty: boolean, busy: boolean, onClose: () => void) {
  const [discard, setDiscard] = useState(false)
  useDraftNavigationGuard(dirty || busy)
  const requestClose = () => {
    if (busy) return
    if (dirty) setDiscard(true)
    else onClose()
  }
  const confirmation = <ConfirmDialog open={discard} title="Discard unsaved changes?"
    description="Your changes in this dialog have not been saved." confirmLabel="Discard changes"
    onClose={() => setDiscard(false)} onConfirm={() => { setDiscard(false); onClose() }} />
  return { requestClose, confirmation }
}
