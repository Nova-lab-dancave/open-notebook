import apiClient from './client'
import type { CreateInfographicRequest, ExplainerJob, ExplainerJobResponse } from '@/lib/types/api'

export const infographicsApi = {
  /** Start generating an infographic; the notes pane follows it via `listJobs`. */
  create: async (notebookId: string, data: CreateInfographicRequest) => {
    const response = await apiClient.post<ExplainerJobResponse>(
      `/notebooks/${notebookId}/infographics`,
      data
    )
    return response.data
  },

  /** Queued/running jobs plus those finished in the last 24 hours, newest first. */
  listJobs: async (notebookId: string) => {
    const response = await apiClient.get<ExplainerJob[]>(`/notebooks/${notebookId}/infographics/jobs`)
    return response.data
  },
}
