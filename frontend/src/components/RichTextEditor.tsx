import { useEffect, useRef, useState } from 'react'
import type { ClipboardEvent } from 'react'
import { normalizeRichText, sanitizeRichText } from '../utils/richText'
import Tooltip from './ui/Tooltip'

type RichTextEditorProps = {
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  ariaLabel?: string
  placeholder?: string
  className?: string
  editorClassName?: string
  disabled?: boolean
}

type ToolbarAction = {
  label: string
  title: string
  command: string
}

const toolbarActions: ToolbarAction[] = [
  { label: 'B', title: 'Bold', command: 'bold' },
  { label: 'I', title: 'Italic', command: 'italic' },
  { label: 'U', title: 'Underline', command: 'underline' },
  { label: '• List', title: 'Bulleted List', command: 'insertUnorderedList' },
  { label: '1. List', title: 'Numbered List', command: 'insertOrderedList' },
  { label: 'Clear', title: 'Clear Formatting', command: 'removeFormat' },
]

export default function RichTextEditor({
  value,
  onChange,
  onBlur,
  placeholder,
  ariaLabel,
  className,
  editorClassName,
  disabled,
}: RichTextEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null)
  const lastValueRef = useRef<string>(normalizeRichText(value))
  const [isFocused, setIsFocused] = useState(false)

  useEffect(() => {
    const nextValue = normalizeRichText(value)
    if (!editorRef.current) return

    if (!isFocused && editorRef.current.innerHTML !== nextValue) {
      editorRef.current.innerHTML = nextValue
    }

    lastValueRef.current = nextValue
  }, [value, isFocused])

  const emitChange = (options?: { sanitize?: boolean }) => {
    if (!editorRef.current) return
    const shouldSanitize = options?.sanitize ?? false
    const sanitized = sanitizeRichText(editorRef.current.innerHTML)
    if (shouldSanitize && sanitized !== editorRef.current.innerHTML) {
      editorRef.current.innerHTML = sanitized
    }
    if (sanitized !== lastValueRef.current) {
      lastValueRef.current = sanitized
      onChange(sanitized)
    }
  }

  const applyCommand = (command: string) => {
    if (!editorRef.current) return
    editorRef.current.focus()
    document.execCommand(command, false)
    emitChange()
  }

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    event.preventDefault()
    const text = event.clipboardData.getData('text/plain')
    document.execCommand('insertText', false, text)
  }

  const editorClasses = [
    'px-3',
    'py-2',
    'text-sm',
    'leading-relaxed',
    'focus:outline-none',
    'focus-visible:ring-2',
    'focus-visible:ring-inset',
    'focus-visible:ring-accent',
    'break-words',
    'min-h-[240px]',
    '[&_ul]:list-disc',
    '[&_ul]:pl-6',
    '[&_ol]:list-decimal',
    '[&_ol]:pl-6',
    '[&_li]:mb-1',
    '[&_p]:mb-2',
  ]

  if (disabled) {
    editorClasses.push('bg-subtle', 'text-muted')
  }

  if (editorClassName) {
    editorClasses.push(editorClassName)
  }

  return (
    <div
      className={`min-w-0 rounded-xl border border-line-strong bg-surface/90 shadow-[0_12px_28px_-24px_rgba(15,23,42,0.65)] ${className || ''}`}
    >
      <div className="flex flex-wrap gap-1 border-b border-line bg-canvas/85 px-2 py-1">
        {toolbarActions.map((action) => (
          <Tooltip key={action.command} content={action.title}><button
            type="button"
            onMouseDown={(event) => {
              event.preventDefault()

            }}
            onClick={() => { if (!disabled) applyCommand(action.command) }}
            className="shrink-0 rounded border border-line bg-surface px-2 py-1 text-xs font-medium text-ink hover:border-brand-line hover:text-accent"
            aria-label={action.title}
            disabled={disabled}
          >
            {action.label}
          </button></Tooltip>
        ))}
      </div>
      <div
        ref={editorRef}
        contentEditable={!disabled}
        tabIndex={disabled ? -1 : 0}
        data-placeholder={placeholder}
        role="textbox"
        aria-multiline="true"
        aria-label={ariaLabel || placeholder || 'Rich text editor'}
        aria-disabled={disabled || undefined}
        suppressContentEditableWarning
        onInput={() => emitChange()}
        onBlur={() => {
          setIsFocused(false)
          emitChange({ sanitize: true })
          onBlur?.()
        }}
        onFocus={() => setIsFocused(true)}
        onPaste={handlePaste}
        className={editorClasses.join(' ')}
      />
    </div>
  )
}
