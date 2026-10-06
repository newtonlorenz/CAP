import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SoAFieldSelector from '../components/SoAFieldSelector'
import { ALL_SOA_FIELD_KEYS, SOA_FIELD_GROUPS } from '../utils/soaFields'

describe('SoAFieldSelector', () => {
  it('renders section toggles', () => {
    render(
      <SoAFieldSelector
        open
        selected={ALL_SOA_FIELD_KEYS}
        onChange={() => {}}
        onClose={() => {}}
        onConfirm={() => {}}
      />
    )

    expect(screen.getAllByText(/select section/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/unselect section/i).length).toBeGreaterThan(0)
    expect(screen.getByText(SOA_FIELD_GROUPS[0].label)).toBeInTheDocument()
  })
})
