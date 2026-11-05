import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useMeetingRecorder } from './use-meeting-recorder'

const mocks = vi.hoisted(() => ({ prepare: vi.fn(), start: vi.fn(), chunk: vi.fn(), finish: vi.fn() }))
vi.mock('@/lib/utils/meeting-audio', () => ({ prepareMeetingCapture: mocks.prepare }))
vi.mock('@/lib/api/meetings', () => ({ meetingsApi: { start: mocks.start, chunk: mocks.chunk, finish: mocks.finish } }))
let onChunk: (audio: Blob) => void
let onEnded: () => void
let captureStop: ReturnType<typeof vi.fn>
const refresh = vi.fn().mockResolvedValue(undefined)
beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn() } })
  vi.stubGlobal('AudioWorkletNode', class {})
  captureStop = vi.fn().mockResolvedValue(undefined)
  mocks.prepare.mockResolvedValue({ start: vi.fn(async (chunk, ended) => { onChunk = chunk; onEnded = ended }), stop: captureStop })
  mocks.start.mockResolvedValue({ id: 'meeting:1' })
  mocks.chunk.mockResolvedValue({})
  mocks.finish.mockResolvedValue({})
})

describe('meeting recorder lifecycle', () => {
  it('survives rerenders and flushes final audio before finishing', async () => {
    const { result, rerender } = renderHook(() => useMeetingRecorder('notebook:1', refresh))
    await act(async () => { await result.current.start('Planning', true) })
    rerender()
    expect(captureStop).not.toHaveBeenCalled()
    act(() => onChunk(new Blob(['first'])))
    captureStop.mockImplementationOnce(async () => { onChunk(new Blob(['last'])) })
    await act(async () => { await result.current.stop() })
    expect(mocks.chunk.mock.calls.map((args) => args[2])).toEqual([0, 1])
    expect(mocks.finish).toHaveBeenCalledWith('notebook:1', 'meeting:1', 2)
    expect(result.current.state).toBe('idle')
  })
  it('reports failed sections and includes their slots in the total', async () => {
    mocks.chunk.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({})
    const { result } = renderHook(() => useMeetingRecorder('notebook:1', refresh))
    await act(async () => { await result.current.start('Planning', false) })
    act(() => { onChunk(new Blob(['first'])); onChunk(new Blob(['next'])) })
    await act(async () => { await result.current.stop() })
    expect(result.current.error).toBe('meetings.chunkFailed')
    expect(mocks.chunk).toHaveBeenCalledTimes(2)
    expect(mocks.finish).toHaveBeenCalledWith('notebook:1', 'meeting:1', 2)
  })
  it('finalizes once if a source ends and stop is clicked', async () => {
    const { result } = renderHook(() => useMeetingRecorder('notebook:1', refresh))
    await act(async () => { await result.current.start('Planning', true) })
    await act(async () => { onEnded(); await result.current.stop() })
    expect(mocks.finish).toHaveBeenCalledTimes(1)
    expect(result.current.error).toBe('meetings.sourceEnded')
  })
  it('cleans up capture and finishes when navigating away', async () => {
    const { result, unmount } = renderHook(() => useMeetingRecorder('notebook:1', refresh))
    await act(async () => { await result.current.start('Planning', false) })
    act(() => onChunk(new Blob(['first'])))
    unmount()
    await waitFor(() => expect(mocks.finish).toHaveBeenCalledWith('notebook:1', 'meeting:1', 1))
    expect(captureStop).toHaveBeenCalledTimes(1)
  })
  it('bounds the backlog and marks dropped audio as missing', async () => {
    let release: () => void = () => {}
    mocks.chunk.mockImplementationOnce(() => new Promise<void>((resolve) => { release = resolve }))
    const { result } = renderHook(() => useMeetingRecorder('notebook:1', refresh))
    await act(async () => { await result.current.start('Planning', false) })
    await act(async () => { for (let i = 0; i < 7; i++) onChunk(new Blob(['chunk'])) })
    expect(captureStop).toHaveBeenCalledTimes(1)
    expect(result.current.error).toBe('meetings.backlog')
    await act(async () => { release(); await result.current.stop() })
    expect(mocks.chunk).toHaveBeenCalledTimes(6)
    expect(mocks.finish).toHaveBeenCalledWith('notebook:1', 'meeting:1', 7)
  })
  it('marks the final section missing when the audio worklet cannot flush', async () => {
    captureStop.mockResolvedValue(false)
    const { result } = renderHook(() => useMeetingRecorder('notebook:1', refresh))
    await act(async () => { await result.current.start('Planning', false) })
    await act(async () => { await result.current.stop() })
    expect(result.current.error).toBe('meetings.chunkFailed')
    expect(mocks.finish).toHaveBeenCalledWith('notebook:1', 'meeting:1', 1)
  })
  it('releases capture if default-model validation fails', async () => {
    mocks.start.mockRejectedValueOnce(new Error('No model'))
    const { result } = renderHook(() => useMeetingRecorder('notebook:1', refresh))
    await act(async () => { await result.current.start('Planning', false) })
    expect(captureStop).toHaveBeenCalledTimes(1)
    expect(mocks.finish).not.toHaveBeenCalled()
    expect(result.current.state).toBe('idle')
  })
})
