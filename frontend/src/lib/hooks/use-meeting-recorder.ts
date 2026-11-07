import { useCallback, useEffect, useRef, useState } from 'react'
import { meetingsApi } from '@/lib/api/meetings'
import { prepareMeetingCapture, type MeetingCapture } from '@/lib/utils/meeting-audio'

const MAX_CHUNKS = 720
const MAX_PENDING = 6

type Session = {
  id: string
  notebook: string
  capture: MeetingCapture
  total: number
  pending: number
  queue: Promise<void>
  stopping?: Promise<void>
  timer?: ReturnType<typeof setInterval>
}

export function useMeetingRecorder(notebookId: string, refresh: () => Promise<void>) {
  const session = useRef<Session | null>(null)
  const starting = useRef(false)
  const alive = useRef(true)
  const [state, setState] = useState<'idle' | 'starting' | 'recording' | 'finishing'>('idle')
  const [activeId, setActiveId] = useState<string | null>(null)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const report = useCallback((key: string) => { if (alive.current) setError(key) }, [])

  const stop = useCallback(async () => {
    const current = session.current
    if (!current) return
    if (current.stopping) return current.stopping
    if (alive.current) setState('finishing')
    current.stopping = (async () => {
      if (current.timer) clearInterval(current.timer)
      const flushed = await current.capture.stop() // Flush before draining.
      if (flushed === false) {
        current.total = Math.min(MAX_CHUNKS, current.total + 1)
        report('meetings.chunkFailed')
      }
      await current.queue
      try {
        await meetingsApi.finish(current.notebook, current.id, current.total)
      } catch {
        report('meetings.finishFailed')
      } finally {
        session.current = null
        if (alive.current) { setState('idle'); setActiveId(null); await refresh() }
      }
    })()
    return current.stopping
  }, [refresh, report])

  const start = useCallback(async (title: string, shared: boolean) => {
    if (starting.current || session.current) return
    starting.current = true
    setState('starting'); setError(null); setSeconds(0)
    let capture: MeetingCapture | undefined
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
        throw new Error('meetings.unsupported')
      }
      capture = await prepareMeetingCapture(shared)
      if (!alive.current) { await capture.stop(); return }
      const meeting = await meetingsApi.start(notebookId, title, shared)
      const current: Session = { id: meeting.id, notebook: notebookId, capture, total: 0, pending: 0, queue: Promise.resolve() }
      session.current = current
      setActiveId(meeting.id)
      const began = Date.now()
      await capture.start((audio) => {
        const sequence = current.total++
        if (sequence >= MAX_CHUNKS) {
          current.total = MAX_CHUNKS
          report('meetings.limitReached'); void stop(); return
        }
        if (current.pending >= MAX_PENDING) {
          report('meetings.backlog'); void stop(); return
        }
        current.pending++
        current.queue = current.queue.then(async () => {
          try {
            await meetingsApi.chunk(current.notebook, current.id, sequence, audio)
          } catch {
            report('meetings.chunkFailed')
          } finally {
            current.pending--
            if (alive.current) await refresh()
          }
        })
      }, () => { report('meetings.sourceEnded'); void stop() })
      if (!alive.current) { await stop(); return }
      setState('recording')
      current.timer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - began) / 1000)
        if (alive.current) setSeconds(elapsed)
        if (elapsed >= 4 * 60 * 60) { report('meetings.limitReached'); void stop() }
      }, 1000)
      await refresh()
    } catch (cause) {
      await capture?.stop()
      session.current = null
      if (alive.current) {
        setState('idle'); setActiveId(null)
        report(cause instanceof Error && cause.message.startsWith('meetings.') ? cause.message : 'meetings.startFailed')
        await refresh()
      }
    } finally {
      starting.current = false
    }
  }, [notebookId, refresh, report, stop])

  useEffect(() => {
    alive.current = true
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (session.current || starting.current) { event.preventDefault(); event.returnValue = '' }
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => {
      alive.current = false
      window.removeEventListener('beforeunload', beforeUnload)
      if (session.current) void stop()
    }
  }, [stop])

  return { state, activeId, seconds, error, start, stop }
}
