type SectionNavProps = {
  label: string
  value: string
  items: readonly { id: string; label: string }[]
  onChange: (value: string) => void
}

/** Page sections keep their drafts mounted; navigation exposes one task at a time. */
export default function SectionNav({ label, value, items, onChange }: SectionNavProps) {
  return (
    <nav aria-label={label} className="cap-page-tabs">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          aria-current={value === item.id ? 'page' : undefined}
          onClick={() => onChange(item.id)}
          className={`min-h-11 border-b-2 px-1 py-2 text-sm font-semibold ${value === item.id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-ink'}`}
        >
          {item.label}
        </button>
      ))}
    </nav>
  )
}
