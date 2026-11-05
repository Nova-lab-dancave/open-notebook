import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ExplainerJob } from '@/lib/types/api'
import { useExplainerJobs, useGenerateExplainer } from './use-explainers'

const create = vi.fn()
const listJobs = vi.fn()
const toast = vi.fn()

vi.mock('@/lib/api/explainers', () => ({
  explainersApi: {
    create: (...a: unknown[]) => create(...a),
    listJobs: (...a: unknown[]) => listJobs(...a),
  },
}))
vi.mock('@/lib/hooks/use-toast', () => ({ useToast: () => ({ toast }) }))

const job = (patch: Partial<ExplainerJob>): ExplainerJob => ({
  job_id: 'command:j1',
  status: 'running',
  requested_at: '2026-11-05T16:00:00Z',
  note_id: null,
  title: null,
  error_message: null,
  ...patch,
})

function wrapperWith(client: QueryClient) {
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return Wrapper
}

describe('useExplainerJobs', () => {
  beforeEach(() => {
    listJobs.mockReset()
    toast.mockReset()
    window.localStorage.clear()
  })

  it('toasts and refreshes notes when a job it saw running completes', async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    listJobs.mockResolvedValueOnce([job({})])
    const hook = renderHook(() => useExplainerJobs('notebook:1'), { wrapper: wrapperWith(client) })
    await waitFor(() => expect(hook.result.current.jobs).toHaveLength(1))
    expect(toast).not.toHaveBeenCalled()

    listJobs.mockResolvedValueOnce([job({ status: 'completed', title: 'Tides', note_id: 'note:1' })])
    await act(async () => {
      await client.refetchQueries({ queryKey: ['explainer-jobs', 'notebook:1'] })
    })
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.objectContaining({ description: 'explainer.ready' })))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['notes', 'notebook:1'] })
    expect(hook.result.current.jobs).toHaveLength(0) // completed jobs show as notes
  })

  it('keeps failures visible until dismissed, without re-toasting old ones', async () => {
    listJobs.mockResolvedValue([job({ status: 'failed', error_message: 'No model configured' })])
    const hook = renderHook(() => useExplainerJobs('notebook:1'), { wrapper: wrapperWith(new QueryClient()) })
    await waitFor(() => expect(hook.result.current.jobs).toHaveLength(1))
    expect(hook.result.current.jobs[0].error_message).toBe('No model configured')
    expect(toast).not.toHaveBeenCalled()

    act(() => hook.result.current.dismiss('command:j1'))
    expect(hook.result.current.jobs).toHaveLength(0)
    expect(JSON.parse(window.localStorage.getItem('explainer-dismissed-jobs') ?? '[]')).toEqual(['command:j1'])
  })

  it('toasts a job that started and failed between two polls', async () => {
    const client = new QueryClient()
    listJobs.mockResolvedValueOnce([])
    const hook = renderHook(() => useExplainerJobs('notebook:1'), { wrapper: wrapperWith(client) })
    await waitFor(() => expect(hook.result.current.isLoading).toBe(false))
    listJobs.mockResolvedValueOnce([job({ status: 'failed', error_message: 'cut off' })])
    await act(async () => {
      await client.refetchQueries({ queryKey: ['explainer-jobs', 'notebook:1'] })
    })
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ description: 'cut off', variant: 'destructive' }))
    )
  })
})

describe('useGenerateExplainer', () => {
  beforeEach(() => {
    create.mockReset().mockResolvedValue({ job_id: 'command:j1', status: 'queued', notebook_id: 'notebook:1' })
    toast.mockReset()
  })

  it('queues a job and refreshes the job list', async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const hook = renderHook(() => useGenerateExplainer('notebook:1'), { wrapper: wrapperWith(client) })
    await act(async () => {
      await hook.result.current.start({ mode: 'sources' })
    })
    expect(create).toHaveBeenCalledWith('notebook:1', { mode: 'sources' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['explainer-jobs', 'notebook:1'] })
  })

  it('rethrows and toasts when the job cannot start', async () => {
    create.mockRejectedValue({ response: { data: { detail: 'Notebook not found' } } })
    const hook = renderHook(() => useGenerateExplainer('notebook:1'), { wrapper: wrapperWith(new QueryClient()) })
    await expect(hook.result.current.start({ mode: 'sources' })).rejects.toBeTruthy()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: 'destructive' }))
  })
})
