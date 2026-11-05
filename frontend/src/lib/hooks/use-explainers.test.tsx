import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useGenerateExplainer } from './use-explainers'

const create = vi.fn()
const waitForCommand = vi.fn()
const toast = vi.fn()

vi.mock('@/lib/api/explainers', () => ({ explainersApi: { create: (...a: unknown[]) => create(...a) } }))
vi.mock('@/lib/api/insights', () => ({
  insightsApi: { waitForCommand: (...a: unknown[]) => waitForCommand(...a) },
}))
vi.mock('@/lib/hooks/use-toast', () => ({ useToast: () => ({ toast }) }))

function setup() {
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useGenerateExplainer('notebook:1'), { wrapper })
  return { hook, invalidate }
}

describe('useGenerateExplainer', () => {
  beforeEach(() => {
    create.mockReset().mockResolvedValue({ job_id: 'command:j1', status: 'queued', notebook_id: 'notebook:1' })
    waitForCommand.mockReset()
    toast.mockReset()
  })

  it('follows the job and refreshes notes when it succeeds', async () => {
    let finish: (v: unknown) => void = () => {}
    waitForCommand.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    const { hook, invalidate } = setup()

    await act(async () => {
      await hook.result.current.start({ mode: 'sources' })
    })
    expect(create).toHaveBeenCalledWith('notebook:1', { mode: 'sources' })
    expect(hook.result.current.pending).toBe(1)

    await act(async () => {
      finish({ status: 'completed', result: { success: true, title: 'Tides' } })
    })
    await waitFor(() => expect(hook.result.current.pending).toBe(0))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['notes', 'notebook:1'] })
    expect(toast).toHaveBeenLastCalledWith(expect.objectContaining({ description: 'explainer.ready' }))
  })

  it('reports a job that finished without success', async () => {
    waitForCommand.mockResolvedValue({ status: 'completed', result: { success: false, error_message: 'cut off' } })
    const { hook, invalidate } = setup()
    await act(async () => {
      await hook.result.current.start({ mode: 'sources' })
    })
    await waitFor(() =>
      expect(toast).toHaveBeenLastCalledWith(
        expect.objectContaining({ description: 'cut off', variant: 'destructive' })
      )
    )
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('rethrows when the job cannot start', async () => {
    create.mockRejectedValue({ response: { data: { detail: 'Notebook not found' } } })
    const { hook } = setup()
    await expect(hook.result.current.start({ mode: 'sources' })).rejects.toBeTruthy()
    expect(waitForCommand).not.toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: 'destructive' }))
  })
})
