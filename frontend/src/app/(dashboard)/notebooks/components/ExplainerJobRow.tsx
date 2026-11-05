'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'

import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { ExplainerJob } from '@/lib/types/api'

// A job still queued after this long usually means no worker is picking it up.
export const QUEUED_WARNING_MS = 60_000

interface ExplainerJobRowProps {
  job: ExplainerJob
  onDismiss: (jobId: string) => void
  /** Injectable clock for tests. */
  now?: number
}

/** A queued, running or failed explainer job in the notes pane. */
export function ExplainerJobRow({ job, onDismiss, now }: ExplainerJobRowProps) {
  const { t } = useTranslation()
  const clock = useClock(job.status === 'queued' && now === undefined)
  const current = now ?? clock

  if (job.status === 'failed') {
    return (
      <div
        className="mb-2 flex items-start gap-2 rounded-md border border-warn/30 bg-warn-tint p-3 text-sm"
        role="alert"
        data-testid="explainer-job-failed"
      >
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{t('explainer.failed')}</p>
          <p className="mt-0.5 break-words text-xs text-muted-foreground">
            {job.error_message || t('apiErrors.genericError')}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 shrink-0 p-0"
          onClick={() => onDismiss(job.job_id)}
          aria-label={t('explainer.dismiss')}
          title={t('explainer.dismiss')}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    )
  }

  const requested = job.requested_at ? Date.parse(job.requested_at) : NaN
  const stuck = job.status === 'queued' && Number.isFinite(requested) && current - requested > QUEUED_WARNING_MS

  return (
    <div
      className="mb-2 flex items-center gap-2 rounded-md border border-dashed border-teal/40 p-3 text-sm text-muted-foreground"
      role="status"
      data-testid="explainer-pending"
    >
      <LoadingSpinner />
      <span>{stuck ? t('explainer.waitingForWorker') : t('explainer.generatingOne')}</span>
    </div>
  )
}

/** Current time, re-read every 10 s while `ticking` (so a stuck queued job gets its warning). */
function useClock(ticking: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!ticking) return
    const id = setInterval(() => setNow(Date.now()), 10_000)
    return () => clearInterval(id)
  }, [ticking])
  return now
}
