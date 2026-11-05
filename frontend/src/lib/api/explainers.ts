import apiClient from './client'
import type { CreateExplainerRequest, ExplainerJobResponse } from '@/lib/types/api'

export const explainersApi = {
  /** Start generating an explainer; poll the returned job via `/commands/jobs/{id}`. */
  create: async (notebookId: string, data: CreateExplainerRequest) => {
    const response = await apiClient.post<ExplainerJobResponse>(
      `/notebooks/${notebookId}/explainers`,
      data
    )
    return response.data
  },
}
