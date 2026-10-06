import { useId, useMemo } from 'react'
import Modal from './Modal'
import Button, { type ButtonVariant } from './Button'

export type DecisionRationaleMode = 'none' | 'optional' | 'required'

export default function DecisionModal(props: {
  open: boolean
  title: string
  description?: string
  confirmLabel: string
  confirmVariant?: ButtonVariant
  dangerDetails?: string[]
  rationaleMode?: DecisionRationaleMode
  rationaleLabel?: string
  rationalePlaceholder?: string
  rationaleValue?: string
  onRationaleChange?: (value: string) => void
  rationaleError?: string | null
  confirmDisabled?: boolean
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
    rationaleMode = 'none',
    rationaleLabel,
    rationalePlaceholder,
    rationaleValue = '',
    onRationaleChange,
    rationaleError,
    confirmDisabled = false,
    onConfirm,
    onClose,
    isWorking,
  } = props

  const trimmedRationale = useMemo(() => rationaleValue.trim(), [rationaleValue])
  const rationaleId = useId()
  const isRationaleRequired = rationaleMode === 'required'
  const hasMissingRequiredRationale = isRationaleRequired && !trimmedRationale
  const displayRationaleError =
    rationaleError ||
    (hasMissingRequiredRationale
      ? (rationaleLabel ? `${rationaleLabel} is required.` : 'Rationale is required.')
      : null)

  return (
    <Modal
      open={open}
      title={title}
      description={description}
      onClose={onClose}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant={confirmVariant}
            onClick={onConfirm}
            loading={isWorking}
            disabled={hasMissingRequiredRationale || confirmDisabled}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {dangerDetails?.length ? (
        <div className="rounded-xl border border-line bg-canvas p-4">
          <div className="text-sm font-semibold text-ink">This will:</div>
          <ul className="mt-2 list-disc pl-5 text-sm text-ink">
            {dangerDetails.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {rationaleMode !== 'none' ? (
        <div className={dangerDetails?.length ? 'mt-4' : ''}>
          <label htmlFor={rationaleId} className="mb-1 block text-sm font-medium text-ink">
            {rationaleLabel || 'Rationale'}
            {isRationaleRequired ? ' *' : ''}
          </label>
          <textarea
            id={rationaleId}
            value={rationaleValue}
            onChange={(event) => onRationaleChange?.(event.target.value)}
            placeholder={
              rationalePlaceholder ||
              (isRationaleRequired
                ? 'Enter required rationale...'
                : 'Enter optional rationale...')
            }
            rows={4}
            className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
          />
          {displayRationaleError ? (
            <div className="mt-1 text-xs text-danger">{displayRationaleError}</div>
          ) : null}
        </div>
      ) : null}
    </Modal>
  )
}
