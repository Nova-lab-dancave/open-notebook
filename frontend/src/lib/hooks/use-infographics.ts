import { infographicsApi } from '@/lib/api/infographics'
import { QUERY_KEYS } from '@/lib/api/query-client'
import type { CreateInfographicRequest } from '@/lib/types/api'
import { type GeneratorConfig, useGenerationJobs, useStartGeneration } from './use-explainers'

const INFOGRAPHIC: GeneratorConfig<CreateInfographicRequest> = {
  queryKey: QUERY_KEYS.infographicJobs,
  listJobs: infographicsApi.listJobs,
  create: infographicsApi.create,
  dismissedKey: 'infographic-dismissed-jobs',
  readyKey: 'infographic.ready',
  failedKey: 'infographic.failed',
  startedKey: 'infographic.started',
}

/** The notebook's infographic jobs: active ones, plus failures until dismissed. */
export function useInfographicJobs(notebookId: string) {
  return useGenerationJobs(notebookId, INFOGRAPHIC)
}

/** Start an infographic job; the notes pane then follows it via useInfographicJobs. */
export function useGenerateInfographic(notebookId: string) {
  return useStartGeneration(notebookId, INFOGRAPHIC)
}
