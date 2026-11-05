import apiClient from './client'
import type { CreateExplainerRequest, ExplainerJob, ExplainerJobResponse } from '@/lib/types/api'

export const explainersApi = {
  /** Start generating an explainer; poll the returned job via `/commands/jobs/{id}`. */
  create: async (notebookId: string, data: CreateExplainerRequest) => {
    const response = await apiClient.post<ExplainerJobResponse>(
      `/notebooks/${notebookId}/explainers`,
      data
    )
    return response.data
  },

  /** Queued/running jobs plus those finished in the last 24 hours, newest first. */
  listJobs: async (notebookId: string) => {
    const response = await apiClient.get<ExplainerJob[]>(`/notebooks/${notebookId}/explainers/jobs`)
    return response.data
  },
}
