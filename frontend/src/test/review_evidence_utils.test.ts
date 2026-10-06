import { describe, it, expect } from 'vitest'
import {
  createPastedScreenshotFilename,
  extractClipboardImageFiles,
  isImageEvidenceFilename,
  normalizeClipboardImageFile,
} from '../utils/reviewEvidence'

describe('reviewEvidence utilities', () => {
  it('detects image evidence filenames by extension', () => {
    expect(isImageEvidenceFilename('evidence.png')).toBe(true)
    expect(isImageEvidenceFilename('evidence.JPG')).toBe(true)
    expect(isImageEvidenceFilename('evidence.txt')).toBe(false)
  })

  it('builds stable screenshot filenames', () => {
    const now = new Date(2026, 2, 16, 15, 30, 45)

    expect(createPastedScreenshotFilename(now)).toBe('screenshot-20260316-153045.png')
    expect(createPastedScreenshotFilename(now, 1)).toBe('screenshot-20260316-153045-2.png')
  })

  it('extracts image files from clipboard items before files fallback', () => {
    const imageFromItems = new File(['item'], 'item.png', { type: 'image/png' })
    const imageFromFiles = new File(['file'], 'file.png', { type: 'image/png' })

    expect(
      extractClipboardImageFiles({
        items: [
          { kind: 'string', type: 'text/plain', getAsFile: () => null },
          { kind: 'file', type: 'image/png', getAsFile: () => imageFromItems },
        ] as unknown as DataTransferItemList,
        files: [imageFromFiles] as unknown as FileList,
      })
    ).toEqual([imageFromItems])

    expect(
      extractClipboardImageFiles({
        items: [] as unknown as DataTransferItemList,
        files: [imageFromFiles] as unknown as FileList,
      })
    ).toEqual([imageFromFiles])
  })

  it('renames pasted png files with the screenshot naming convention', async () => {
    const source = new File(['png-data'], 'clipboard.png', { type: 'image/png' })
    const now = new Date(2026, 2, 16, 15, 30, 45)

    const normalized = await normalizeClipboardImageFile(source, { now })

    expect(normalized.name).toBe('screenshot-20260316-153045.png')
    expect(normalized.type).toBe('image/png')
    expect(normalized.size).toBe(source.size)
  })
})
