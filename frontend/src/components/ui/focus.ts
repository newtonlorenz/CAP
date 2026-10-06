// Shared by dialogs and menus so keyboard navigation includes rich text and disclosures.
export function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(
    'a[href],button,input,textarea,select,summary,[contenteditable="true"],[tabindex]'
  )).filter((element) => {
    if ((element.tabIndex < 0 && !element.matches('[contenteditable="true"]:not([tabindex="-1"])')) || element.matches(':disabled,[type="hidden"]')) return false
    for (let node: HTMLElement | null = element; node; node = node.parentElement) {
      if (node.tagName === 'DETAILS' && !node.hasAttribute('open') && !node.querySelector('summary')?.contains(element)) return false
      if (node.hidden || node.hasAttribute('inert') || node.getAttribute('aria-hidden') === 'true') return false
      const style = getComputedStyle(node)
      if (style.display === 'none' || style.visibility === 'hidden') return false
    }
    return true
  })
}
