'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'

import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { ExplainerJob } from '@/lib/types/api'
import { NOTE_CARD_CLASS } from './NoteCard'

// A job still queued after this long usually means no worker is picking it up.
export const QUEUED_WARNING_MS = 60_000

interface ExplainerJobRowProps {
  job: ExplainerJob
  onDismiss: (jobId: string) => void
  /** Injectable clock for tests. */
  now?: number
}

/** A queued, running or failed explainer job, as a square card in the notes grid. */
export function ExplainerJobRow({ job, onDismiss, now }: ExplainerJobRowProps) {
  const { t } = useTranslation()
  const clock = useClock(job.status === 'queued' && now === undefined)
  const current = now ?? clock

  if (job.status === 'failed') {
    return (
      <div
        className={`${NOTE_CARD_CLASS} gap-2 border-warn/30 bg-warn-tint text-sm`}
        role="alert"
        data-testid="explainer-job-failed"
      >
        <AlertTriangle className="h-5 w-5 shrink-0 text-warn" aria-hidden />
        <p className="pr-6 font-medium">{t('explainer.failed')}</p>
        <p
          className="min-h-0 flex-1 overflow-y-auto text-xs text-muted-foreground [overflow-wrap:anywhere]"
          title={job.error_message || undefined}
        >
          {job.error_message || t('apiErrors.genericError')}
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="absolute right-1.5 top-1.5 h-6 w-6 p-0"
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
      className={`${NOTE_CARD_CLASS} items-center justify-center gap-3 border-dashed border-teal/40 text-center text-sm text-muted-foreground`}
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
