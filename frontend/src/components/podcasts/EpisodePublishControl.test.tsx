import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

import { EpisodePublishControl } from './EpisodePublishControl'
import type { PodcastEpisode } from '@/lib/types/podcasts'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const publish = vi.fn()
const unpublish = vi.fn()
let publishPending = false
let unpublishPending = false

vi.mock('@/lib/hooks/use-podcasts', () => ({
  usePublishPodcastEpisode: () => ({ mutate: publish, isPending: publishPending }),
  useUnpublishPodcastEpisode: () => ({ mutate: unpublish, isPending: unpublishPending }),
}))

function makeEpisode(overrides: Partial<PodcastEpisode> = {}): PodcastEpisode {
  return {
    id: 'episode:1',
    name: 'Offline first',
    episode_profile: {} as PodcastEpisode['episode_profile'],
    speaker_profile: {} as PodcastEpisode['speaker_profile'],
    briefing: 'INTERNAL generation prompt',
    job_status: 'completed',
    audio_url: '/api/podcasts/episodes/episode:1/audio',
    outline: {
      segments: [
        { name: 'Intro', description: 'Why   offline\nfirst matters.' },
        { name: 'Deep dive', description: 'How sync conflicts resolve.' },
      ],
    },
    ...overrides,
  }
}

beforeEach(() => {
  publish.mockReset()
  unpublish.mockReset()
  publishPending = false
  unpublishPending = false
})

function nothingRendered(episode: PodcastEpisode) {
  const { container } = render(<EpisodePublishControl episode={episode} />)
  expect(container).toBeEmptyDOMElement()
}

describe('EpisodePublishControl visibility', () => {
  it.each(['running', 'pending', 'failed', 'submitted'] as const)(
    'renders nothing for a %s episode',
    (status) => {
      nothingRendered(makeEpisode({ job_status: status }))
    }
  )

  it('renders nothing for a completed episode with no audio', () => {
    nothingRendered(makeEpisode({ audio_url: null, audio_file: null }))
  })

  it('is offered for a completed episode whose audio is a stored file', () => {
    render(<EpisodePublishControl episode={makeEpisode({ audio_url: null, audio_file: 'episodes/1/a.mp3' })} />)

    expect(screen.getByRole('button', { name: 'podcasts.feed.publish' })).toBeInTheDocument()
  })
})

describe('EpisodePublishControl publishing', () => {
  function openDialog(episode = makeEpisode()) {
    render(<EpisodePublishControl episode={episode} />)
    fireEvent.click(screen.getByRole('button', { name: 'podcasts.feed.publish' }))
    return screen.getByRole('dialog')
  }

  it('publishes nothing until the dialog is confirmed', () => {
    openDialog()

    expect(publish).not.toHaveBeenCalled()
  })

  it('pre-fills the summary from the outline with whitespace collapsed', () => {
    const dialog = openDialog()

    expect(within(dialog).getByRole('textbox')).toHaveValue(
      'Why offline first matters. How sync conflicts resolve.'
    )
  })

  it('never uses the generation briefing as the summary', () => {
    const dialog = openDialog()

    const value = (within(dialog).getByRole('textbox') as HTMLTextAreaElement).value
    expect(value).not.toContain('INTERNAL')
    expect(value).not.toBe('')
  })

  it('cuts a long outline at a word boundary with an ellipsis', () => {
    const dialog = openDialog(makeEpisode({ outline: { segments: [{ description: 'word '.repeat(200) }] } }))

    const value = (within(dialog).getByRole('textbox') as HTMLTextAreaElement).value
    expect(value.length).toBeLessThanOrEqual(300)
    expect(value.endsWith('word…')).toBe(true)
  })

  it('falls back to the episode name when there is no outline', () => {
    const dialog = openDialog(makeEpisode({ outline: null }))

    expect(within(dialog).getByRole('textbox')).toHaveValue('Offline first')
  })

  it('publishes with the edited summary on confirm', () => {
    const dialog = openDialog()

    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'My own show notes' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'podcasts.feed.publishConfirm' }))

    expect(publish).toHaveBeenCalledTimes(1)
    expect(publish.mock.calls[0][0]).toEqual({ episodeId: 'episode:1', summary: 'My own show notes' })
  })

  it('closes the dialog once publishing succeeds', () => {
    const dialog = openDialog()
    publish.mockImplementation((_vars, options) => options?.onSuccess?.())

    fireEvent.click(within(dialog).getByRole('button', { name: 'podcasts.feed.publishConfirm' }))

    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('stays open, keeping the text, when publishing is refused', () => {
    const dialog = openDialog()
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'Edited notes' } })
    publish.mockImplementation(() => undefined) // onSuccess never fires

    fireEvent.click(within(dialog).getByRole('button', { name: 'podcasts.feed.publishConfirm' }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(within(screen.getByRole('dialog')).getByRole('textbox')).toHaveValue('Edited notes')
  })

  it('does nothing on cancel', () => {
    const dialog = openDialog()

    fireEvent.click(within(dialog).getByRole('button', { name: 'common.cancel' }))

    expect(publish).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('blocks confirm for a summary over 4000 characters and says why', () => {
    const dialog = openDialog()

    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'x'.repeat(4001) } })

    expect(within(dialog).getByRole('button', { name: 'podcasts.feed.publishConfirm' })).toBeDisabled()
    expect(within(dialog).getByText('podcasts.feed.summaryTooLong')).toBeInTheDocument()
  })

  it('accepts exactly 4000 characters', () => {
    const dialog = openDialog()

    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'x'.repeat(4000) } })

    expect(within(dialog).getByRole('button', { name: 'podcasts.feed.publishConfirm' })).toBeEnabled()
  })

  it('disables confirm while a publish request is pending', () => {
    publishPending = true
    const dialog = openDialog()

    expect(within(dialog).getByRole('button', { name: 'podcasts.feed.publishing' })).toBeDisabled()
  })
})

describe('EpisodePublishControl for a published episode', () => {
  const published = () => makeEpisode({ published_at: '2026-11-08T12:00:00+00:00' })

  it('shows that it is in the feed and offers Unpublish instead of Publish', () => {
    render(<EpisodePublishControl episode={published()} />)

    expect(screen.getByText('podcasts.feed.inFeed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'podcasts.feed.unpublish' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'podcasts.feed.publish' })).toBeNull()
  })

  it('unpublishes straight away, without a confirmation', () => {
    render(<EpisodePublishControl episode={published()} />)

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.feed.unpublish' }))

    expect(unpublish).toHaveBeenCalledTimes(1)
    expect(unpublish.mock.calls[0][0]).toBe('episode:1')
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })

  it('disables Unpublish while the request is pending', () => {
    unpublishPending = true
    render(<EpisodePublishControl episode={published()} />)

    expect(screen.getByRole('button', { name: 'podcasts.feed.unpublishing' })).toBeDisabled()
  })

  it('stays visible for a published episode that is no longer playable, so it can be pulled', () => {
    render(<EpisodePublishControl episode={{ ...published(), audio_url: null, audio_file: null }} />)

    expect(screen.getByRole('button', { name: 'podcasts.feed.unpublish' })).toBeInTheDocument()
  })
})
