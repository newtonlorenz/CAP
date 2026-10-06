import { useState, type ClipboardEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import { useToast } from '../../contexts/ToastContext'
import { extractClipboardImageFiles, normalizeClipboardImageFile } from '../../utils/reviewEvidence'
import { notifyApiError } from '../../utils/notify'

export function useReviewEvidenceFiles(cycleId: string | undefined, active: boolean) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [uploadingCounts, setUploadingCounts] = useState<Record<string, number>>({})
  const [deletingFileId, setDeletingFileId] = useState<string | null>(null)

  const upload = useMutation({
    mutationFn: async ({ itemId, file }: { itemId: string; file: File }) => {
      const formData = new FormData()
      formData.append('file', file)
      await api.post(`/review-cycles/${cycleId}/items/${itemId}/files`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    },
    onMutate: ({ itemId }) => setUploadingCounts((prev) => ({ ...prev, [itemId]: (prev[itemId] || 0) + 1 })),
    onSettled: (_data, _error, variables) => {
      if (!variables) return
      setUploadingCounts((prev) => {
        const next = { ...prev }
        const count = (next[variables.itemId] || 1) - 1
        if (count <= 0) delete next[variables.itemId]
        else next[variables.itemId] = count
        return next
      })
    },
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['review-cycle', cycleId] }) },
    onError: (error: unknown) => notifyApiError(toast, error, 'File upload failed'),
  })

  const remove = useMutation({
    mutationFn: async ({ itemId, fileId }: { itemId: string; fileId: string }) => {
      await api.delete(`/review-cycles/${cycleId}/items/${itemId}/files/${fileId}`)
    },
    onMutate: ({ fileId }) => setDeletingFileId(fileId),
    onSettled: () => setDeletingFileId(null),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['review-cycle', cycleId] }) },
    onError: (error: unknown) => notifyApiError(toast, error, 'File delete failed'),
  })

  const queueFiles = (itemId: string, files: File[]) => files.forEach((file) => upload.mutate({ itemId, file }))

  const handlePaste = (itemId: string, event: ClipboardEvent<HTMLElement>) => {
    if (!active) return
    const imageFiles = extractClipboardImageFiles(event.clipboardData)
    if (!imageFiles.length) return
    event.preventDefault()
    void (async () => {
      const now = new Date()
      const results = await Promise.allSettled(imageFiles.map((file, sequence) => normalizeClipboardImageFile(file, { now, sequence })))
      const files = results.filter((result): result is PromiseFulfilledResult<File> => result.status === 'fulfilled').map((result) => result.value)
      const failedCount = results.length - files.length
      if (failedCount) toast.error('Screenshot paste failed', { description: failedCount === imageFiles.length
        ? 'Clipboard image could not be processed.'
        : `${failedCount} screenshot${failedCount === 1 ? '' : 's'} could not be processed.` })
      if (files.length) queueFiles(itemId, files)
    })()
  }

  const downloadFile = async (itemId: string, fileId: string, filename: string) => {
    const response = await api.get(`/review-cycles/${cycleId}/items/${itemId}/files/${fileId}/download`, { responseType: 'blob' })
    const blobUrl = window.URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(blobUrl)
  }

  return { uploadingCounts, deletingFileId, queueFiles, handlePaste, downloadFile, deleteFile: remove.mutate }
}
