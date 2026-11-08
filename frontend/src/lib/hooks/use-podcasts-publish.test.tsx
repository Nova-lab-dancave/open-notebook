import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { QUERY_KEYS } from '@/lib/api/query-client'
import { usePublishPodcastEpisode, useUnpublishPodcastEpisode } from './use-podcasts'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const publishEpisode = vi.fn()
const unpublishEpisode = vi.fn()
const toast = vi.fn()

vi.mock('@/lib/api/podcasts', () => ({
  podcastsApi: {
    publishEpisode: (...a: unknown[]) => publishEpisode(...a),
    unpublishEpisode: (...a: unknown[]) => unpublishEpisode(...a),
  },
}))
vi.mock('@/lib/hooks/use-toast', () => ({ useToast: () => ({ toast }) }))

/** What axios throws for an HTTP error response. */
function httpError(status: number, detail: string) {
  return Object.assign(new Error(detail), {
    isAxiosError: true,
    response: { status, data: { detail } },
  })
}

/** A client configured like the app's (mutations retry once by default). */
function appLikeClient() {
  return new QueryClient({ defaultOptions: { mutations: { retry: 1, retryDelay: 0 } } })
}

function wrapperWith(client: QueryClient) {
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return Wrapper
}

beforeEach(() => {
  publishEpisode.mockReset()
  unpublishEpisode.mockReset()
  toast.mockReset()
})

describe('usePublishPodcastEpisode', () => {
  it('publishes with the edited summary, refreshes the episode lists and says so', async () => {
    const client = appLikeClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    publishEpisode.mockResolvedValue({ published_at: '2026-11-08T12:00:00+00:00' })
    const { result } = renderHook(() => usePublishPodcastEpisode(), { wrapper: wrapperWith(client) })

    await act(async () => {
      await result.current.mutateAsync({ episodeId: 'episode:1', summary: 'My notes' })
    })

    expect(publishEpisode).toHaveBeenCalledWith('episode:1', 'My notes')
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.podcastEpisodes })
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'podcasts.feed.published' }))
  })

  it('lets the server pick the summary when none is given', async () => {
    publishEpisode.mockResolvedValue({})
    const { result } = renderHook(() => usePublishPodcastEpisode(), {
      wrapper: wrapperWith(appLikeClient()),
    })

    await act(async () => {
      await result.current.mutateAsync({ episodeId: 'episode:1' })
    })

    expect(publishEpisode).toHaveBeenCalledWith('episode:1', undefined)
  })

  it('shows the server\'s reason when publishing is refused, and refreshes nothing', async () => {
    const client = appLikeClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    publishEpisode.mockRejectedValue(
      httpError(400, "Unsupported audio format '.wav': only .mp3 and .m4a episodes can be published.")
    )
    const { result } = renderHook(() => usePublishPodcastEpisode(), { wrapper: wrapperWith(client) })

    await act(async () => {
      await result.current.mutateAsync({ episodeId: 'episode:1' }).catch(() => undefined)
    })

    expect(toast).toHaveBeenCalledWith({
      title: 'podcasts.feed.publishFailed',
      description: "Unsupported audio format '.wav': only .mp3 and .m4a episodes can be published.",
      variant: 'destructive',
    })
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('does not retry a refused publish behind the scenes', async () => {
    publishEpisode.mockRejectedValue(httpError(400, 'Audio file not found on disk.'))
    const { result } = renderHook(() => usePublishPodcastEpisode(), {
      wrapper: wrapperWith(appLikeClient()),
    })

    await act(async () => {
      await result.current.mutateAsync({ episodeId: 'episode:1' }).catch(() => undefined)
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(publishEpisode).toHaveBeenCalledTimes(1)
  })
})

describe('useUnpublishPodcastEpisode', () => {
  it('unpublishes, refreshes the episode lists and says so', async () => {
    const client = appLikeClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    unpublishEpisode.mockResolvedValue(undefined)
    const { result } = renderHook(() => useUnpublishPodcastEpisode(), { wrapper: wrapperWith(client) })

    await act(async () => {
      await result.current.mutateAsync('episode:1')
    })

    expect(unpublishEpisode).toHaveBeenCalledWith('episode:1')
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.podcastEpisodes })
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'podcasts.feed.unpublished' }))
  })

  it('shows the server\'s reason when unpublishing fails, and refreshes nothing', async () => {
    const client = appLikeClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    unpublishEpisode.mockRejectedValue(httpError(500, 'Failed to unpublish episode'))
    const { result } = renderHook(() => useUnpublishPodcastEpisode(), { wrapper: wrapperWith(client) })

    await act(async () => {
      await result.current.mutateAsync('episode:1').catch(() => undefined)
    })

    expect(toast).toHaveBeenCalledWith({
      title: 'podcasts.feed.unpublishFailed',
      description: 'Failed to unpublish episode',
      variant: 'destructive',
    })
    expect(invalidate).not.toHaveBeenCalled()
    expect(unpublishEpisode).toHaveBeenCalledTimes(1)
  })
})
