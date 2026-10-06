import { expect, it } from 'vitest'
import { getApiErrorMessage } from '../api/errors'

it('shows the actual submission blockers returned by the server', () => {
  const error = { isAxiosError: true, response: { status: 400, data: { detail: { gates: ['Close the submission review.', 'Include the required evidence.'] } } } }
  expect(getApiErrorMessage(error, 'Request failed')).toBe('Close the submission review.; Include the required evidence.')
})
