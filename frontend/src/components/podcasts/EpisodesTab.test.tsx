import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { EpisodesTab } from './EpisodesTab'
import type { PodcastEpisode } from '@/lib/types/podcasts'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const completed: PodcastEpisode[] = [
  { id: 'episode:1', name: 'First done', job_status: 'completed' } as PodcastEpisode,
  { id: 'episode:2', name: 'Second done', job_status: 'completed' } as PodcastEpisode,
]
const running: PodcastEpisode[] = [
  { id: 'episode:3', name: 'In progress', job_status: 'running' } as PodcastEpisode,
]

vi.mock('@/lib/hooks/use-podcasts', () => ({
  usePodcastEpisodes: () => ({
    episodes: [...completed, ...running],
    statusGroups: { running, pending: [], completed, failed: [] },
    statusCounts: { total: 3, running: 1, pending: 0, completed: 2, failed: 0 },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    isFetching: false,
  }),
  useDeletePodcastEpisode: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRetryPodcastEpisode: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('@/components/podcasts/EpisodeCard', () => ({
  EpisodeCard: ({ episode }: { episode: PodcastEpisode }) => <div>{episode.name}</div>,
}))
vi.mock('@/components/podcasts/GeneratePodcastDialog', () => ({ GeneratePodcastDialog: () => null }))
vi.mock('@/components/podcasts/ReadScriptDialog', () => ({ ReadScriptDialog: () => null }))

describe('EpisodesTab completed section', () => {
  it('starts collapsed and opens into a two-column grid', () => {
    render(<EpisodesTab />)

    // Other sections stay open.
    expect(screen.getByText('In progress')).toBeInTheDocument()
    // Completed list is collapsed by default.
    expect(screen.queryByText('First done')).toBeNull()

    fireEvent.click(screen.getByText('podcasts.showEpisodes'))

    const first = screen.getByText('First done')
    expect(screen.getByText('Second done')).toBeInTheDocument()
    expect(first.parentElement).toHaveClass('md:grid-cols-2')
    expect(screen.getByText('podcasts.hideEpisodes')).toBeInTheDocument()
  })
})
