'use client'

import { useState } from 'react'
import { Mic, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useMeetings } from '@/lib/hooks/use-meetings'
import { useMeetingRecorder } from '@/lib/hooks/use-meeting-recorder'
import { meetingsApi, type Meeting, type MeetingEdit } from '@/lib/api/meetings'

export function NotebookMeetings({ notebookId }: { notebookId: string }) {
  const { t } = useTranslation()
  const meetings = useMeetings(notebookId)
  const recorder = useMeetingRecorder(notebookId, meetings.refresh)
  const [shared, setShared] = useState(false)
  const [title, setTitle] = useState('')
  const busy = recorder.state !== 'idle'
  return (
    <section className="mb-4 space-y-3 rounded-md border p-3" aria-label={t('meetings.heading')}>
      <h3 className="text-sm font-semibold">{t('meetings.heading')}</h3>
      <p className="text-xs text-muted-foreground">{t('meetings.privacy')}</p>
      <p className="text-xs text-muted-foreground">{t('meetings.browserHelp')}</p>
      <Input aria-label={t('meetings.title')} placeholder={t('meetings.title')} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} disabled={busy} />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} disabled={busy} />
        {t('meetings.shareAudio')}
      </label>
      <p className="text-xs text-muted-foreground">{shared ? t('meetings.sharedHelp') : t('meetings.micHelp')}</p>
      {recorder.state === 'idle' ? (
        <Button size="sm" onClick={() => void recorder.start(title.trim() || t('meetings.defaultTitle'), shared)}>
          <Mic className="mr-2 h-4 w-4" />{t('meetings.record')}
        </Button>
      ) : (
        <div className="flex flex-wrap items-center gap-2" role="status">
          <span className="text-sm">{t(({ starting: 'meetings.starting', recording: 'meetings.recording', finishing: 'meetings.finishing', idle: 'meetings.recording' })[recorder.state])} {Math.floor(recorder.seconds / 60)}:{String(recorder.seconds % 60).padStart(2, '0')}</span>
          {recorder.state === 'recording' ? (
            <Button size="sm" variant="outline" onClick={() => void recorder.stop()}><Square className="mr-2 h-4 w-4" />{t('meetings.stop')}</Button>
          ) : <LoadingSpinner />}
        </div>
      )}
      {recorder.error && <p role="alert" className="text-sm text-destructive">{t(recorder.error)}</p>}
      {meetings.isError && <p role="alert" className="text-sm text-destructive">{t('meetings.loadFailed')} <Button variant="link" onClick={() => void meetings.refetch()}>{t('common.retry')}</Button></p>}
      {meetings.isLoading && <LoadingSpinner />}
      {meetings.data?.map((meeting) => (
        <MeetingCard key={meeting.id} meeting={meeting} notebookId={notebookId}
          active={meeting.id === recorder.activeId} busy={meetings.action.isPending}
          run={(operation) => meetings.action.mutate(operation)} />
      ))}
    </section>
  )
}

function MeetingCard({ meeting, notebookId, active, busy, run }: {
  meeting: Meeting; notebookId: string; active: boolean; busy: boolean
  run: (operation: () => Promise<unknown>) => void
}) {
  const { t } = useTranslation()
  const [edit, setEdit] = useState<MeetingEdit | null>(null)
  const [discard, setDiscard] = useState(false)
  const pending = ['new', 'queued', 'running'].includes(meeting.summary_status)
  const actions = edit?.actions ?? meeting.actions
  const updateAction = (index: number, patch: Partial<Meeting['actions'][number]>) => {
    if (!edit) return
    setEdit({ ...edit, actions: edit.actions.map((a, i) => i === index ? { ...a, ...patch } : a) })
  }
  return (
    <article className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{meeting.title}</h4>
        <span className="text-xs text-muted-foreground">{t(({ review: 'meetings.toReview', recording: 'meetings.recording', approved: 'meetings.approved' })[meeting.status])}</span>
      </div>
      {meeting.interrupted && <p role="alert" className="text-sm text-warn">{t('meetings.interrupted')}</p>}
      {meeting.missing_chunks.length > 0 && <p role="alert" className="text-sm text-warn">{t('meetings.missing', { count: meeting.missing_chunks.length })}</p>}
      {meeting.status === 'recording' && !active && (
        <div className="space-y-2">
          <p className="text-sm text-warn">{t('meetings.interrupted')}</p>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => meetingsApi.finish(notebookId, meeting.id, meeting.total_chunks, true))}>{t('meetings.recover')}</Button>
        </div>
      )}
      {pending && <p className="text-sm text-teal" role="status">{t('meetings.summarizing')}</p>}
      {meeting.summary_error && <p role="alert" className="text-sm text-destructive">{t('meetings.summaryFailed')}</p>}
      {edit && <Input aria-label={t('meetings.title')} value={edit.title} maxLength={200} onChange={(e) => setEdit({ ...edit, title: e.target.value })} />}
      <Tabs defaultValue={meeting.status === 'recording' ? 'transcript' : 'summary'}>
        <TabsList className="flex h-auto flex-wrap">
          <TabsTrigger value="summary">{t('meetings.summary')}</TabsTrigger>
          <TabsTrigger value="actions">{t('meetings.actions')}</TabsTrigger>
          <TabsTrigger value="transcript">{t('meetings.transcript')}</TabsTrigger>
        </TabsList>
        <TabsContent value="summary">
          {edit ? <Textarea aria-label={t('meetings.summary')} value={edit.summary} maxLength={30000} onChange={(e) => setEdit({ ...edit, summary: e.target.value })} rows={8} /> : <p className="whitespace-pre-wrap break-words text-sm">{meeting.summary || t('meetings.noSummary')}</p>}
        </TabsContent>
        <TabsContent value="actions" className="space-y-3">
          {!actions.length && <p className="text-sm text-muted-foreground">{t('meetings.noActions')}</p>}
          {actions.map((action, i) => (
            <div key={i} className="space-y-1 rounded-md border p-2">
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={action.done} disabled={!edit} onChange={(e) => updateAction(i, { done: e.target.checked })} />
                {edit ? <Input aria-label={t('meetings.action')} value={action.text} maxLength={2000} onChange={(e) => updateAction(i, { text: e.target.value })} /> : <span>{action.text}</span>}
              </label>
              {edit ? <>
                <Input aria-label={t('meetings.owner')} placeholder={t('meetings.owner')} value={action.owner} maxLength={200} onChange={(e) => updateAction(i, { owner: e.target.value })} />
                <Input aria-label={t('meetings.due')} placeholder={t('meetings.due')} value={action.due} maxLength={200} onChange={(e) => updateAction(i, { due: e.target.value })} />
                <Button variant="ghost" size="sm" onClick={() => setEdit({ ...edit, actions: edit.actions.filter((_, n) => n !== i) })}>{t('common.remove')}</Button>
              </> : <p className="text-xs text-muted-foreground">{[action.owner, action.due].filter(Boolean).join(' · ')}</p>}
              <blockquote className="border-l-2 pl-2 text-xs text-muted-foreground">{action.evidence}</blockquote>
            </div>
          ))}
        </TabsContent>
        <TabsContent value="transcript">{edit ? <Textarea aria-label={t('meetings.transcript')} value={edit.transcript} maxLength={400000} onChange={(e) => setEdit({ ...edit, transcript: e.target.value })} rows={12} /> : <p className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-sm">{meeting.transcript || t('meetings.waitingTranscript')}</p>}</TabsContent>
      </Tabs>
      <div className="flex flex-wrap gap-2">
        {meeting.status !== 'recording' && <>
          {edit ? <>
            <Button size="sm" disabled={busy || !edit.title.trim() || !edit.transcript.trim() || edit.actions.some((a) => !a.text.trim())} onClick={() => run(async () => { await meetingsApi.edit(notebookId, meeting.id, edit); setEdit(null) })}>{t('common.save')}</Button>
            <Button size="sm" variant="ghost" onClick={() => setEdit(null)}>{t('common.cancel')}</Button>
          </> : <>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setEdit({ revision: meeting.revision, title: meeting.title, transcript: meeting.transcript, summary: meeting.summary, actions: meeting.actions.map((a) => ({ ...a })) })}>{t('common.edit')}</Button>
            {meeting.status === 'review' && <Button size="sm" disabled={busy || !meeting.transcript} onClick={() => run(() => meetingsApi.approve(notebookId, meeting.id))}>{t('meetings.approve')}</Button>}
            {meeting.status === 'review' && <Button size="sm" variant="outline" disabled={busy || pending} onClick={() => run(() => meetingsApi.summarize(notebookId, meeting.id))}>{t('meetings.retrySummary')}</Button>}
          </>}
        </>}
        {meeting.status !== 'approved' && !active && <Button size="sm" variant="ghost" className="text-destructive" disabled={busy} onClick={() => setDiscard(true)}>{t('meetings.discard')}</Button>}
      </div>
      <ConfirmDialog open={discard} onOpenChange={setDiscard} title={t('meetings.discard')} description={t('meetings.discardConfirm')} confirmText={t('meetings.discard')} confirmVariant="destructive" onConfirm={() => { setDiscard(false); run(() => meetingsApi.discard(notebookId, meeting.id)) }} />
    </article>
  )
}
