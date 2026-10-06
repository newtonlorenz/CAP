import { useQuery } from '@tanstack/react-query'
import api from '../api/client'

export type InstallationCapabilities = {
  ai: { enabled: boolean; provider: string; model: string | null; external_processing: boolean }
  jev?: { enabled: boolean; model: string; external_processing: boolean; revision: number }
  pdf_structure?: {
    engine: 'native' | 'opendataloader'
    available: boolean
    local_only: true
  }
  email: { enabled: boolean; mode: 'disabled' | 'smtp' | 'log' }
  ocr: { enabled: boolean; available: boolean }
  feedback: { enabled: boolean }
}

export function useCapabilities() {
  return useQuery({
    queryKey: ['installation-capabilities'],
    queryFn: async () => (await api.get<InstallationCapabilities>('/capabilities')).data,
    staleTime: 60_000,
    retry: false,
  })
}
