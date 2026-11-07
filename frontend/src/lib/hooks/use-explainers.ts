import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { explainersApi } from '@/lib/api/explainers'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import type { CreateExplainerRequest, ExplainerJob, ExplainerJobResponse } from '@/lib/types/api'

// Generation takes minutes; poll gently, and only while a job is active.
export const EXPLAINER_POLL_MS = 4000

export const isActiveExplainerJob = (job: ExplainerJob) =>
  job.status === 'queued' || job.status === 'running'

/**
 * A notebook generator whose jobs show in the notes pane (explainers,
 * infographics). Keys are i18n keys for the toasts.
 */
export interface GeneratorConfig<Req> {
  queryKey: (notebookId: string) => readonly unknown[]
  listJobs: (notebookId: string) => Promise<ExplainerJob[]>
  create: (notebookId: string, data: Req) => Promise<ExplainerJobResponse>
  /** localStorage key for failures the user dismissed. */
  dismissedKey: string
  readyKey: string
  failedKey: string
  startedKey: string
}

const EXPLAINER: GeneratorConfig<CreateExplainerRequest> = {
  queryKey: QUERY_KEYS.explainerJobs,
  listJobs: explainersApi.listJobs,
  create: explainersApi.create,
  dismissedKey: 'explainer-dismissed-jobs',
  readyKey: 'explainer.ready',
  failedKey: 'explainer.failed',
  startedKey: 'explainer.started',
}

/** The notebook's explainer jobs (see useGenerationJobs). */
export function useExplainerJobs(notebookId: string) {
  return useGenerationJobs(notebookId, EXPLAINER)
}

/** Start an explainer job; the notes pane then follows it via useExplainerJobs. */
export function useGenerateExplainer(notebookId: string) {
  return useStartGeneration(notebookId, EXPLAINER)
}

/**
 * A generator's jobs from the server, so a job stays visible across reloads
 * and navigation, and a failure stays on screen with its reason.
 *
 * When a job this view saw as active finishes, the notes list is refreshed
 * and a toast says whether it worked. Jobs that were already finished when the
 * view loaded don't toast again.
 */
export function useGenerationJobs<Req>(notebookId: string, config: GeneratorConfig<Req>) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const { readyKey, failedKey, dismissedKey } = config

  const query = useQuery({
    queryKey: config.queryKey(notebookId),
    queryFn: () => config.listJobs(notebookId),
    enabled: !!notebookId,
    refetchInterval: (q) => (q.state.data?.some(isActiveExplainerJob) ? EXPLAINER_POLL_MS : false),
  })

  const seen = useRef<Map<string, ExplainerJob['status']> | null>(null)
  useEffect(() => {
    const jobs = query.data
    if (!jobs) return
    const previous = seen.current
    seen.current = new Map(jobs.map((job) => [job.job_id, job.status]))
    if (!previous) return // first load: nothing has changed yet

    let finished = false
    for (const job of jobs) {
      const before = previous.get(job.job_id)
      // A job missing from the previous poll was started since (and may have
      // finished between polls); one seen finished before has already toasted.
      const wasActive = before === undefined || before === 'queued' || before === 'running'
      if (!wasActive || isActiveExplainerJob(job)) continue
      finished = true
      if (job.status === 'completed') {
        toast({ title: t('common.success'), description: t(readyKey, { title: job.title ?? '' }) })
      } else {
        toast({
          title: t(failedKey),
          description: job.error_message || t('apiErrors.genericError'),
          variant: 'destructive',
        })
      }
    }
    if (finished) {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notes(notebookId) })
    }
  }, [query.data, notebookId, queryClient, t, toast, readyKey, failedKey])

  const [dismissed, setDismissed] = useState<string[]>(() => readDismissed(dismissedKey))
  const dismiss = useCallback(
    (jobId: string) => {
      setDismissed((ids) => {
        const next = [...ids.filter((id) => id !== jobId), jobId].slice(-50)
        writeDismissed(dismissedKey, next)
        return next
      })
    },
    [dismissedKey]
  )

  const jobs = (query.data ?? []).filter(
    (job) => isActiveExplainerJob(job) || (job.status === 'failed' && !dismissed.includes(job.job_id))
  )
  return { jobs, dismiss, isLoading: query.isLoading }
}

/** Start a generator job; the notes pane then follows it via useGenerationJobs. */
export function useStartGeneration<Req>(notebookId: string, config: GeneratorConfig<Req>) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const [isStarting, setIsStarting] = useState(false)
  const { create, queryKey, startedKey, failedKey } = config

  /** Resolves once the job is queued (not when it finishes); throws on failure. */
  const start = useCallback(
    async (data: Req) => {
      setIsStarting(true)
      try {
        const job = await create(notebookId, data)
        toast({ title: t('common.success'), description: t(startedKey) })
        await queryClient.invalidateQueries({ queryKey: queryKey(notebookId) })
        return job
      } catch (error) {
        toast({
          title: t(failedKey),
          description: getApiErrorMessage(error, t, failedKey),
          variant: 'destructive',
        })
        throw error
      } finally {
        setIsStarting(false)
      }
    },
    [notebookId, queryClient, t, toast, create, queryKey, startedKey, failedKey]
  )

  return { start, isStarting }
}

// Dismissed failures are a per-browser convenience; storage may be unavailable.
function readDismissed(key: string): string[] {
  try {
    const raw = window.localStorage.getItem(key)
    const ids = raw ? JSON.parse(raw) : []
    return Array.isArray(ids) ? ids.filter((id) => typeof id === 'string') : []
  } catch {
    return []
  }
}

function writeDismissed(key: string, ids: string[]) {
  try {
    window.localStorage.setItem(key, JSON.stringify(ids))
  } catch {
    // ignore
  }
}
