import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { FeedUrlPanel } from './FeedUrlPanel'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const getFeedUrl = vi.fn()
const rotateFeedToken = vi.fn()
const toast = vi.fn()

vi.mock('@/lib/api/podcasts', () => ({
  podcastsApi: {
    getFeedUrl: (...a: unknown[]) => getFeedUrl(...a),
    rotateFeedToken: (...a: unknown[]) => rotateFeedToken(...a),
  },
}))
vi.mock('@/lib/hooks/use-toast', () => ({ useToast: () => ({ toast }) }))

const URL_ONE = 'https://lab.example.ts.net:8502/api/podcasts/feed/tokenONE/feed.xml'
const URL_TWO = 'https://lab.example.ts.net:8502/api/podcasts/feed/tokenTWO/feed.xml'

/** What axios throws for an HTTP error response. */
function httpError(status: number, detail: string) {
  return Object.assign(new Error(detail), {
    isAxiosError: true,
    response: { status, data: { detail } },
  })
}

function renderPanel() {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <FeedUrlPanel />
    </QueryClientProvider>
  )
}

const writeText = vi.fn()

beforeEach(() => {
  getFeedUrl.mockReset()
  rotateFeedToken.mockReset()
  toast.mockReset()
  writeText.mockReset().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
})

describe('FeedUrlPanel with a feed URL', () => {
  it('shows the feed URL in a read-only field', async () => {
    getFeedUrl.mockResolvedValue({ feed_url: URL_ONE })

    renderPanel()

    const field = await screen.findByDisplayValue(URL_ONE)
    expect(field).toHaveAttribute('readonly')
  })

  it('copies the URL to the clipboard and says so', async () => {
    getFeedUrl.mockResolvedValue({ feed_url: URL_ONE })
    renderPanel()
    await screen.findByDisplayValue(URL_ONE)

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.feed.copy' }))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(URL_ONE))
    expect(await screen.findByText('podcasts.feed.copied')).toBeInTheDocument()
  })
})

describe('FeedUrlPanel rotating the token', () => {
  async function openRotateDialog() {
    getFeedUrl.mockResolvedValue({ feed_url: URL_ONE })
    renderPanel()
    await screen.findByDisplayValue(URL_ONE)
    fireEvent.click(screen.getByRole('button', { name: 'podcasts.feed.rotate' }))
    return screen.findByRole('alertdialog')
  }

  it('asks first, with the warning that subscriptions will break, and calls nothing yet', async () => {
    const dialog = await openRotateDialog()

    expect(within(dialog).getByText('podcasts.feed.rotateWarning')).toBeInTheDocument()
    expect(rotateFeedToken).not.toHaveBeenCalled()
  })

  it('rotates on confirm and shows the new URL in place of the old one', async () => {
    rotateFeedToken.mockResolvedValue({ feed_url: URL_TWO })
    const dialog = await openRotateDialog()

    fireEvent.click(within(dialog).getByRole('button', { name: 'podcasts.feed.rotateConfirm' }))

    expect(await screen.findByDisplayValue(URL_TWO)).toBeInTheDocument()
    expect(screen.queryByDisplayValue(URL_ONE)).toBeNull()
    expect(rotateFeedToken).toHaveBeenCalledTimes(1)
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'podcasts.feed.rotated' }))
  })

  it('does nothing when cancelled', async () => {
    const dialog = await openRotateDialog()

    fireEvent.click(within(dialog).getByRole('button', { name: 'common.cancel' }))

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(rotateFeedToken).not.toHaveBeenCalled()
    expect(screen.getByDisplayValue(URL_ONE)).toBeInTheDocument()
  })

  it('keeps the old URL and tells the user when rotating fails', async () => {
    rotateFeedToken.mockRejectedValue(httpError(500, 'Failed to rotate the feed token'))
    const dialog = await openRotateDialog()

    fireEvent.click(within(dialog).getByRole('button', { name: 'podcasts.feed.rotateConfirm' }))

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'podcasts.feed.rotateFailed', variant: 'destructive' })
      )
    )
    expect(screen.getByDisplayValue(URL_ONE)).toBeInTheDocument()
  })
})

describe('FeedUrlPanel without a usable URL', () => {
  it('explains that an HTTPS address is needed and offers no URL, copy or rotate', async () => {
    getFeedUrl.mockRejectedValue(
      httpError(422, 'The Podcast Feed needs an HTTPS address. Set OPEN_NOTEBOOK_PUBLIC_URL ...')
    )

    renderPanel()

    expect(await screen.findByText('podcasts.feed.needsHttpsTitle')).toBeInTheDocument()
    expect(screen.getByText('podcasts.feed.needsHttpsDesc')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'podcasts.feed.copy' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'podcasts.feed.rotate' })).toBeNull()
  })

  it('shows a plain failure message for any other error', async () => {
    getFeedUrl.mockRejectedValue(httpError(500, 'Failed to get the feed URL'))

    renderPanel()

    expect(await screen.findByText('podcasts.feed.loadFailed')).toBeInTheDocument()
    expect(screen.queryByText('podcasts.feed.needsHttpsTitle')).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('does not retry a rejected request behind the scenes', async () => {
    getFeedUrl.mockRejectedValue(httpError(422, 'needs https'))

    renderPanel()
    await screen.findByText('podcasts.feed.needsHttpsTitle')

    expect(getFeedUrl).toHaveBeenCalledTimes(1)
  })
})
