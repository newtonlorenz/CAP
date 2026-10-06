import Button from './Button'

export default function LoadError({ subject, onRetry }: { subject: string; onRetry: () => void }) {
  return <div role="alert" className="rounded-lg border border-danger-line bg-danger-soft p-4 text-sm text-danger">
    <p>{subject} could not be loaded. Try again to retrieve the latest information.</p>
    <Button className="mt-3" size="sm" onClick={onRetry}>Try again</Button>
  </div>
}
