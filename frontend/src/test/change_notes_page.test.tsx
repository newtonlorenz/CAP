import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ChangeNotes from '../pages/ChangeNotes'

describe('Change notes', () => {
  it('opens the current version first and keeps its feature changes readable', () => {
    render(<ChangeNotes />)

    expect(screen.getByRole('heading', { name: 'Change notes', level: 1 })).toBeInTheDocument()
    const versions = screen.getAllByRole('heading', { level: 2 })
    expect(versions.map(heading => heading.textContent)).toEqual(['Version 2026.10.07.2', 'Version 2026.10.07', 'Version 2026.10.03', 'Version 2026.10.02'])
    const current = versions[0].closest('details')!
    expect(current).toHaveAttribute('open')
    expect(within(current).getByText('Current version')).toBeInTheDocument()
    expect(within(current).getByText('7 Oct 2026')).toHaveAttribute('datetime', '2026-10-07')
    expect(within(current).getByRole('heading', { name: 'Requirement evidence access', level: 3 })).toBeVisible()
  })

  it('lets users expand the previous version without closing the current release', () => {
    render(<ChangeNotes />)

    const previousHeading = screen.getByRole('heading', { name: 'Version 2026.10.02', level: 2 })
    const previous = previousHeading.closest('details')!
    expect(previous).not.toHaveAttribute('open')
    fireEvent.click(previousHeading.closest('summary')!)
    expect(previous).toHaveAttribute('open')
    expect(within(previous).getByRole('heading', { name: 'Profile and account settings', level: 3 })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Version 2026.10.07.2', level: 2 }).closest('details')).toHaveAttribute('open')
  })
})
