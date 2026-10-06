import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import GuideFaq from '../pages/GuideFaq'

describe('GuideFaq Page', () => {
  it('opens matching topics and FAQ answers, handles no results and restores navigation', () => {
    render(<MemoryRouter><GuideFaq /></MemoryRouter>)
    const search = screen.getByRole('searchbox', { name: 'Search the guide' })
    fireEvent.change(search, { target: { value: 'component register' } })
    expect(screen.getByRole('link', { name: /open change management/i })).toBeVisible()
    expect(screen.getByText(/what is the difference between the component register/i).closest('details')).toHaveAttribute('open')
    expect(screen.queryByRole('navigation', { name: 'Main workflows' })).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'Jev' } })
    const importAnswer = screen.getByText(/is jev required for question imports/i).closest('details')!
    expect(importAnswer).toHaveAttribute('open')
    expect(within(importAnswer).getByText(/normal imports and manual preparation work without Jev/i)).toBeVisible()

    fireEvent.change(search, { target: { value: 'no such guidance xyz' } })
    expect(screen.getByText(/no guidance matches/i)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(search).toHaveValue('')
    expect(screen.getByRole('navigation', { name: 'Main workflows' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Shared requirements' })).toBeVisible()
  })

  it('offers the three primary journeys and preserves contextual destinations', () => {
    render(<MemoryRouter><GuideFaq /></MemoryRouter>)
    const workflows = within(screen.getByRole('navigation', { name: 'Main workflows' }))
    const destinations = [
      ['Licence Applications', '/licence-applications'],
      ['Certifications', '/certification-projects'],
      ['Change Management', '/change-management'],
    ]
    expect(workflows.getAllByRole('link')).toHaveLength(destinations.length)
    for (const [name, href] of destinations) {
      expect(workflows.getByRole('link', { name: new RegExp(name) })).toHaveAttribute('href', href)
      const section = screen.getByRole('heading', { name }).closest('details')!
      expect(section).not.toHaveAttribute('open')
      fireEvent.click(section.querySelector('summary')!)
      expect(within(section).getByRole('link', { name: `Open ${name}` })).toBeVisible()
    }

    for (const [title, link, href] of [
      ['Shared requirements', 'Open Requirements', '/requirements'],
      ['Requirement assessments', 'Open Requirement assessments', '/review-cycles'],
      ['Blank forms, imports and existing forms', 'Open Existing forms', '/library?section=forms'],
      ['Teams and sharing', 'Open Teams', '/access-teams'],
    ]) {
      const section = screen.getByRole('heading', { name: title }).closest('details')!
      fireEvent.click(section.querySelector('summary')!)
      expect(within(section).getByRole('link', { name: link })).toHaveAttribute('href', href)
    }
  })
})
