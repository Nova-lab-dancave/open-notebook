import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { explainersApi } from '@/lib/api/explainers'
import { insightsApi } from '@/lib/api/insights'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import type { CreateExplainerRequest } from '@/lib/types/api'

// Explainers take minutes; poll gently.
const POLL_INTERVAL_MS = 4000

interface ExplainerJobResult {
  success?: boolean
  title?: string | null
  error_message?: string | null
}

/**
 * Start explainer jobs for a notebook and follow them until they finish.
 *
 * `pending` counts jobs this view is still waiting on. When one finishes the
 * notes list is refreshed and a toast says whether it worked. Polling stops if
 * the view unmounts; the job keeps running on the server and its note shows up
 * the next time the notes load.
 */
export function useGenerateExplainer(notebookId: string) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const [pending, setPending] = useState(0)
  const [isStarting, setIsStarting] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    abortRef.current = controller
    return () => controller.abort()
  }, [])

  const follow = useCallback(
    async (jobId: string) => {
      const signal = abortRef.current?.signal
      setPending((n) => n + 1)
      try {
        const status = await insightsApi.waitForCommand(jobId, {
          intervalMs: POLL_INTERVAL_MS,
          signal,
        })
        if (signal?.aborted || !status) return
        const result = (status.result ?? {}) as ExplainerJobResult
        if (status.status === 'completed' && result.success !== false) {
          queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notes(notebookId) })
          toast({
            title: t('common.success'),
            description: t('explainer.ready', { title: result.title ?? '' }),
          })
        } else {
          toast({
            title: t('explainer.failed'),
            description: result.error_message || status.error_message || t('apiErrors.genericError'),
            variant: 'destructive',
          })
        }
      } finally {
        if (!signal?.aborted) setPending((n) => Math.max(0, n - 1))
      }
    },
    [notebookId, queryClient, t, toast]
  )

  /** Submit a job. Resolves once it is queued (not when it finishes); throws on failure. */
  const start = useCallback(
    async (data: CreateExplainerRequest) => {
      setIsStarting(true)
      try {
        const job = await explainersApi.create(notebookId, data)
        toast({ title: t('common.success'), description: t('explainer.started') })
        void follow(job.job_id)
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
    [follow, notebookId, t, toast]
  )

  return { start, pending, isStarting }
}
