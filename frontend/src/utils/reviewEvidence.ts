const IMAGE_EVIDENCE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg'])

type ClipboardLike = Pick<DataTransfer, 'items' | 'files'>

type NormalizeOptions = {
  now?: Date
  sequence?: number
}

export function getEvidenceFileExtension(filename: string): string {
  const dotIndex = filename.lastIndexOf('.')
  if (dotIndex < 0) return ''
  return filename.slice(dotIndex).toLowerCase()
}

export function isImageEvidenceFilename(filename: string): boolean {
  return IMAGE_EVIDENCE_EXTENSIONS.has(getEvidenceFileExtension(filename))
}

export function buildReviewItemEvidencePreviewUrl(
  cycleId: string,
  itemId: string,
  fileId: string
): string {
  return `${import.meta.env.BASE_URL}api/v1/review-cycles/${cycleId}/items/${itemId}/files/${fileId}/preview`
}

export function createPastedScreenshotFilename(now = new Date(), sequence = 0): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const hours = String(now.getHours()).padStart(2, '0')
  const minutes = String(now.getMinutes()).padStart(2, '0')
  const seconds = String(now.getSeconds()).padStart(2, '0')
  const suffix = sequence > 0 ? `-${sequence + 1}` : ''
  return `screenshot-${year}${month}${day}-${hours}${minutes}${seconds}${suffix}.png`
}

export function extractClipboardImageFiles(clipboardData: ClipboardLike | null): File[] {
  if (!clipboardData) return []

  const filesFromItems = Array.from(clipboardData.items || [])
    .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file))

  if (filesFromItems.length) {
    return filesFromItems
  }

  return Array.from(clipboardData.files || []).filter((file) => file.type.startsWith('image/'))
}

function canvasToPngBlob(canvas: HTMLCanvasElement | OffscreenCanvas): Promise<Blob> {
  if (typeof OffscreenCanvas !== 'undefined' && canvas instanceof OffscreenCanvas) {
    return canvas.convertToBlob({ type: 'image/png' })
  }

  return new Promise<Blob>((resolve, reject) => {
    const htmlCanvas = canvas as HTMLCanvasElement
    htmlCanvas.toBlob((blob) => {
      if (blob) {
        resolve(blob)
        return
      }
      reject(new Error('Canvas export failed'))
    }, 'image/png')
  })
}

async function drawImageToPngBlob(source: File): Promise<Blob> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(source)
    try {
      const canvas =
        typeof OffscreenCanvas !== 'undefined'
          ? new OffscreenCanvas(bitmap.width, bitmap.height)
          : document.createElement('canvas')
      canvas.width = bitmap.width
      canvas.height = bitmap.height
      const context = canvas.getContext('2d') as
        | CanvasRenderingContext2D
        | OffscreenCanvasRenderingContext2D
        | null
      if (!context) {
        throw new Error('Canvas context unavailable')
      }
      context.drawImage(bitmap, 0, 0)
      return await canvasToPngBlob(canvas)
    } finally {
      bitmap.close()
    }
  }

  if (typeof document === 'undefined') {
    throw new Error('Clipboard image conversion is unavailable')
  }

  return new Promise<Blob>((resolve, reject) => {
    const image = new Image()
    const objectUrl = URL.createObjectURL(source)

    image.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = image.naturalWidth || image.width
      canvas.height = image.naturalHeight || image.height
      const context = canvas.getContext('2d') as CanvasRenderingContext2D | null
      if (!context) {
        URL.revokeObjectURL(objectUrl)
        reject(new Error('Canvas context unavailable'))
        return
      }
      context.drawImage(image, 0, 0)
      void canvasToPngBlob(canvas)
        .then(resolve)
        .catch(reject)
        .finally(() => URL.revokeObjectURL(objectUrl))
    }

    image.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      reject(new Error('Image load failed'))
    }

    image.src = objectUrl
  })
}

export async function normalizeClipboardImageFile(
  source: File,
  options: NormalizeOptions = {}
): Promise<File> {
  const now = options.now || new Date()
  const sequence = options.sequence || 0
  const filename = createPastedScreenshotFilename(now, sequence)

  if (source.type === 'image/png') {
    return new File([source], filename, {
      type: 'image/png',
      lastModified: now.getTime(),
    })
  }

  const pngBlob = await drawImageToPngBlob(source)
  return new File([pngBlob], filename, {
    type: 'image/png',
    lastModified: now.getTime(),
  })
}
