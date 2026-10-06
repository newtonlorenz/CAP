import DecisionModal from './DecisionModal'
import { type ButtonVariant } from './Button'

export default function ConfirmDialog(props: {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  confirmVariant?: ButtonVariant
  dangerDetails?: string[]
  onConfirm: () => void
  onClose: () => void
  isWorking?: boolean
}) {
  const {
    open,
    title,
    description,
    confirmLabel,
    confirmVariant = 'destructive',
    dangerDetails,
    onConfirm,
    onClose,
    isWorking,
  } = props

  return (
    <DecisionModal
      open={open}
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      confirmVariant={confirmVariant}
      dangerDetails={dangerDetails}
      rationaleMode="none"
      onConfirm={onConfirm}
      onClose={onClose}
      isWorking={isWorking}
    />
  )
}
