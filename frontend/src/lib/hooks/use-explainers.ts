import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { explainersApi } from '@/lib/api/explainers'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import type { CreateExplainerRequest, ExplainerJob } from '@/lib/types/api'

// Explainers take minutes; poll gently, and only while a job is active.
export const EXPLAINER_POLL_MS = 4000
const DISMISSED_KEY = 'explainer-dismissed-jobs'

export const isActiveExplainerJob = (job: ExplainerJob) =>
  job.status === 'queued' || job.status === 'running'

/**
 * The notebook's explainer jobs from the server, so a job stays visible across
 * reloads and navigation, and a failure stays on screen with its reason.
 *
 * When a job this view saw as active finishes, the notes list is refreshed
 * and a toast says whether it worked. Jobs that were already finished when the
 * view loaded don't toast again.
 */
export function useExplainerJobs(notebookId: string) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  const query = useQuery({
    queryKey: QUERY_KEYS.explainerJobs(notebookId),
    queryFn: () => explainersApi.listJobs(notebookId),
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
        toast({ title: t('common.success'), description: t('explainer.ready', { title: job.title ?? '' }) })
      } else {
        toast({
          title: t('explainer.failed'),
          description: job.error_message || t('apiErrors.genericError'),
          variant: 'destructive',
        })
      }
    }
    if (finished) {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notes(notebookId) })
    }
  }, [query.data, notebookId, queryClient, t, toast])

  const [dismissed, setDismissed] = useState<string[]>(() => readDismissed())
  const dismiss = useCallback((jobId: string) => {
    setDismissed((ids) => {
      const next = [...ids.filter((id) => id !== jobId), jobId].slice(-50)
      writeDismissed(next)
      return next
    })
  }, [])

  const jobs = (query.data ?? []).filter(
    (job) => isActiveExplainerJob(job) || (job.status === 'failed' && !dismissed.includes(job.job_id))
  )
  return { jobs, dismiss, isLoading: query.isLoading }
}

/** Start an explainer job; the notes pane then follows it via useExplainerJobs. */
export function useGenerateExplainer(notebookId: string) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const [isStarting, setIsStarting] = useState(false)

  /** Resolves once the job is queued (not when it finishes); throws on failure. */
  const start = useCallback(
    async (data: CreateExplainerRequest) => {
      setIsStarting(true)
      try {
        const job = await explainersApi.create(notebookId, data)
        toast({ title: t('common.success'), description: t('explainer.started') })
        await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.explainerJobs(notebookId) })
        return job
      } catch (error) {
        toast({
          title: t('explainer.failed'),
          description: getApiErrorMessage(error, t, 'explainer.failed'),
          variant: 'destructive',
        })
        throw error
      } finally {
        setIsStarting(false)
      }
    },
    [notebookId, queryClient, t, toast]
  )

  return { start, isStarting }
}

// Dismissed failures are a per-browser convenience; storage may be unavailable.
function readDismissed(): string[] {
  try {
    const raw = window.localStorage.getItem(DISMISSED_KEY)
    const ids = raw ? JSON.parse(raw) : []
    return Array.isArray(ids) ? ids.filter((id) => typeof id === 'string') : []
  } catch {
    return []
  }
}

function writeDismissed(ids: string[]) {
  try {
    window.localStorage.setItem(DISMISSED_KEY, JSON.stringify(ids))
  } catch {
    // ignore
  }
}
