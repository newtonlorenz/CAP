// Sorting helpers for requirement reference IDs like:
// "12", "12.1", "12.10", "G.1", and occasionally "12." (trailing dot).

const splitReferenceId = (value: string) => {
  const cleaned = value.trim().replace(/\.+$/, '')
  return cleaned.split('.').filter(Boolean)
}

export const compareReferenceIds = (left: string, right: string) => {
  const leftParts = splitReferenceId(left)
  const rightParts = splitReferenceId(right)
  const maxDepth = Math.max(leftParts.length, rightParts.length)

  for (let index = 0; index < maxDepth; index += 1) {
    const leftPart = leftParts[index]
    const rightPart = rightParts[index]

    if (leftPart === undefined) return -1
    if (rightPart === undefined) return 1

    const leftIsNumber = /^\d+$/.test(leftPart)
    const rightIsNumber = /^\d+$/.test(rightPart)

    if (leftIsNumber && rightIsNumber) {
      const diff = Number(leftPart) - Number(rightPart)
      if (diff !== 0) return diff
      continue
    }

    // Keep numeric sections before non-numeric (e.g. "12" before "G").
    if (leftIsNumber && !rightIsNumber) return -1
    if (!leftIsNumber && rightIsNumber) return 1

    const textDiff = leftPart.localeCompare(rightPart)
    if (textDiff !== 0) return textDiff
  }

  return 0
}

