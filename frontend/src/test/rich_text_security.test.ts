import { describe, expect, it } from 'vitest'
import { normalizeRichText, sanitizeRichText } from '../utils/richText'

describe('rich-text rendering boundaries', () => {
  it.each([
    '<custom><img src=x onerror="alert(1)"><b onclick="alert(1)">Keep</b></custom>',
    '<svg><g onload="alert(1)"></g></svg><p>Keep</p>',
    '<math><mtext><img src=x onerror="alert(1)"></mtext></math><p>Keep</p>',
    '<form><p><a href="javascript:alert(1)">Keep</a></p></form>',
  ])('sanitises nested and malformed markup while retaining text', (source) => {
    const output = sanitizeRichText(source)
    const container = document.createElement('div')
    container.innerHTML = output
    expect(container.textContent).toContain('Keep')
    expect(container.querySelector('img,svg,math,script,form,a')).toBeNull()
    expect([...container.querySelectorAll('*')].every((el) => el.attributes.length === 0)).toBe(true)
  })

  it('retains supported review formatting and escapes plain text', () => {
    expect(normalizeRichText('<p><strong>Policy</strong></p><ul><li>Retain records</li></ul>'))
      .toBe('<p><strong>Policy</strong></p><ul><li>Retain records</li></ul>')
    expect(normalizeRichText('A & B\nSecond line')).toBe('A &amp; B<br>Second line')
  })
})
