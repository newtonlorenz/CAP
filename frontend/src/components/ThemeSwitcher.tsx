import { useTheme, type ThemePreference } from '../hooks/useTheme'
import Tooltip from './ui/Tooltip'

const options: { value: ThemePreference; label: string; path: React.ReactNode }[] = [
  { value: 'light', label: 'Light', path: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></> },
  { value: 'dark', label: 'Dark', path: <path d="M20.9 13.1A9 9 0 0 1 10.9 3 9 9 0 1 0 20.9 13.1Z" /> },
  { value: 'system', label: 'System', path: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8m-4-4v4" /></> },
]

export default function ThemeSwitcher() {
  const { preference, setPreference } = useTheme()
  return (
    <div className="theme-switcher" role="group" aria-label="Appearance">
      {options.map(({ value, label, path }) => (
        <Tooltip key={value} content={`${label} theme`}><button type="button" aria-label={`Use ${value} theme`}
          aria-pressed={preference === value} onClick={() => setPreference(value)}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{path}</svg>
        </button></Tooltip>
      ))}
    </div>
  )
}
