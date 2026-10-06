import Modal from './ui/Modal'
import Button from './ui/Button'

type ReviewerDisplay = 'both' | 'names' | 'emails'

type ReviewCycleReportOptionsProps = {
  open: boolean
  value: ReviewerDisplay
  onChange: (value: ReviewerDisplay) => void
  onClose: () => void
  onConfirm: () => void
  title?: string
}

const options: Array<{ value: ReviewerDisplay; label: string; description: string }> = [
  {
    value: 'both',
    label: 'Names + emails',
    description: 'Include full name and email address for reviewers.',
  },
  {
    value: 'names',
    label: 'Names only',
    description: 'Use full names without emails.',
  },
  {
    value: 'emails',
    label: 'Emails only',
    description: 'Use email addresses only.',
  },
]

export default function ReviewCycleReportOptions({
  open,
  value,
  onChange,
  onClose,
  onConfirm,
  title = 'Review Report Options',
}: ReviewCycleReportOptionsProps) {
  return (
    <Modal open={open} title={title} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" onClick={onConfirm}>Download</Button></>}>
      <fieldset className="space-y-4">
        <legend className="mb-4 text-sm text-muted">Choose how reviewers appear in the report.</legend>
        {options.map((option) => <label key={option.value} className="flex cursor-pointer items-start gap-3 text-sm text-ink">
          <input type="radio" name="reviewer-display" value={option.value} checked={value === option.value}
            onChange={() => onChange(option.value)} className="mt-1" />
          <span><span className="block font-semibold">{option.label}</span><span className="mt-1 block text-xs text-muted">{option.description}</span></span>
        </label>)}
      </fieldset>
    </Modal>
  )
}
