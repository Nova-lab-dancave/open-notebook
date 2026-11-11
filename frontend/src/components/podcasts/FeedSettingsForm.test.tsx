import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { FeedSettingsForm } from './FeedSettingsForm'
import type { PodcastFeedSettings } from '@/lib/types/podcasts'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const getFeedSettings = vi.fn()
const updateFeedSettings = vi.fn()
const uploadFeedArtwork = vi.fn()
const getFeedArtwork = vi.fn()
const toast = vi.fn()

vi.mock('@/lib/api/podcasts', () => ({
  podcastsApi: {
    getFeedSettings: (...a: unknown[]) => getFeedSettings(...a),
    updateFeedSettings: (...a: unknown[]) => updateFeedSettings(...a),
    uploadFeedArtwork: (...a: unknown[]) => uploadFeedArtwork(...a),
    getFeedArtwork: (...a: unknown[]) => getFeedArtwork(...a),
  },
}))
vi.mock('@/lib/hooks/use-toast', () => ({ useToast: () => ({ toast }) }))

const SAVED: PodcastFeedSettings = {
  title: 'Open Notebook Podcasts',
  author: 'Open Notebook',
  description: 'Podcast episodes generated in Open Notebook.',
  language: 'en',
  has_artwork: false,
  artwork_version: null,
}

/** What axios throws for an HTTP error response. */
function httpError(status: number, detail: string) {
  return Object.assign(new Error(detail), {
    isAxiosError: true,
    response: { status, data: { detail } },
  })
}

function renderForm() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <FeedSettingsForm />
    </QueryClientProvider>
  )
}

const field = (label: string) => screen.findByLabelText(label) as Promise<HTMLInputElement>
const saveButton = () => screen.getByRole('button', { name: 'podcasts.feedSettings.save' })
const pngFile = (name = 'cover.png', type = 'image/png', size = 1024) =>
  new File([new Uint8Array(size)], name, { type })

function chooseFile(file: File) {
  const input = screen.getByLabelText('podcasts.feedSettings.chooseArtwork', { selector: 'input' })
  fireEvent.change(input, { target: { files: [file] } })
}

beforeEach(() => {
  for (const mock of [getFeedSettings, updateFeedSettings, uploadFeedArtwork, getFeedArtwork, toast]) {
    mock.mockReset()
  }
  getFeedSettings.mockResolvedValue(SAVED)
  getFeedArtwork.mockResolvedValue(new Blob(['png'], { type: 'image/png' }))
  let n = 0
  vi.stubGlobal('URL', Object.assign(URL, {
    createObjectURL: vi.fn(() => `blob:preview-${++n}`),
    revokeObjectURL: vi.fn(),
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FeedSettingsForm saved values', () => {
  it('loads the saved show details into the fields', async () => {
    renderForm()

    expect(await field('podcasts.feedSettings.titleLabel')).toHaveValue('Open Notebook Podcasts')
    expect(await field('podcasts.feedSettings.authorLabel')).toHaveValue('Open Notebook')
    expect(await field('podcasts.feedSettings.descriptionLabel')).toHaveValue(
      'Podcast episodes generated in Open Notebook.'
    )
    expect(await field('podcasts.feedSettings.languageLabel')).toHaveValue('en')
  })

  it('shows a plain message, and no form, when the settings cannot be loaded', async () => {
    getFeedSettings.mockRejectedValue(httpError(500, 'Failed to read the feed settings'))

    renderForm()

    expect(await screen.findByText('podcasts.feedSettings.loadFailed')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).toBeNull()
  })
})

describe('FeedSettingsForm saving', () => {
  it('has nothing to save until a field changes', async () => {
    renderForm()
    await field('podcasts.feedSettings.titleLabel')

    expect(saveButton()).toBeDisabled()
  })

  it('sends only the fields that changed', async () => {
    updateFeedSettings.mockResolvedValue({ ...SAVED, title: "Dan's Lab Radio" })
    renderForm()

    fireEvent.change(await field('podcasts.feedSettings.titleLabel'), { target: { value: "Dan's Lab Radio" } })
    fireEvent.click(saveButton())

    await waitFor(() => expect(updateFeedSettings).toHaveBeenCalledTimes(1))
    expect(updateFeedSettings).toHaveBeenCalledWith({ title: "Dan's Lab Radio" })
  })

  it('says it saved, and is back to having nothing to save', async () => {
    updateFeedSettings.mockResolvedValue({ ...SAVED, author: 'Dan' })
    renderForm()

    fireEvent.change(await field('podcasts.feedSettings.authorLabel'), { target: { value: 'Dan' } })
    fireEvent.click(saveButton())

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'podcasts.feedSettings.saved' }))
    )
    await waitFor(() => expect(saveButton()).toBeDisabled())
    expect(await field('podcasts.feedSettings.authorLabel')).toHaveValue('Dan')
  })

  it('sends a blank value so the server can go back to the default', async () => {
    updateFeedSettings.mockResolvedValue(SAVED)
    renderForm()

    fireEvent.change(await field('podcasts.feedSettings.titleLabel'), { target: { value: '' } })
    fireEvent.click(saveButton())

    await waitFor(() => expect(updateFeedSettings).toHaveBeenCalledWith({ title: '' }))
  })

  it("shows the server's reason when it refuses, and keeps what was typed", async () => {
    updateFeedSettings.mockRejectedValue(
      httpError(400, "The show language must be a language code such as 'en' or 'pt-BR'.")
    )
    renderForm()

    fireEvent.change(await field('podcasts.feedSettings.languageLabel'), { target: { value: 'english' } })
    fireEvent.click(saveButton())

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith({
        title: 'podcasts.feedSettings.saveFailed',
        description: "The show language must be a language code such as 'en' or 'pt-BR'.",
        variant: 'destructive',
      })
    )
    expect(await field('podcasts.feedSettings.languageLabel')).toHaveValue('english')
    expect(saveButton()).toBeEnabled()
  })

  it('does not send the request twice if it fails', async () => {
    updateFeedSettings.mockRejectedValue(httpError(500, 'Failed to update the feed settings'))
    renderForm()

    fireEvent.change(await field('podcasts.feedSettings.titleLabel'), { target: { value: 'X' } })
    fireEvent.click(saveButton())
    await waitFor(() => expect(toast).toHaveBeenCalled())

    expect(updateFeedSettings).toHaveBeenCalledTimes(1)
  })
})

describe('FeedSettingsForm artwork', () => {
  it('says there is no artwork yet, and fetches no preview', async () => {
    renderForm()

    expect(await screen.findByText('podcasts.feedSettings.noArtwork')).toBeInTheDocument()
    expect(screen.queryByRole('img')).toBeNull()
    expect(getFeedArtwork).not.toHaveBeenCalled()
  })

  it('shows a preview of the current artwork', async () => {
    getFeedSettings.mockResolvedValue({ ...SAVED, has_artwork: true, artwork_version: 'abc123' })

    renderForm()

    const preview = await screen.findByRole('img', { name: 'podcasts.feedSettings.artworkAlt' })
    expect(preview).toHaveAttribute('src', 'blob:preview-1')
  })

  it('uploads the chosen file, says so, and shows the new preview', async () => {
    uploadFeedArtwork.mockResolvedValue({ ...SAVED, has_artwork: true, artwork_version: 'v2' })
    renderForm()
    await screen.findByText('podcasts.feedSettings.noArtwork')
    const file = pngFile()

    chooseFile(file)

    await waitFor(() => expect(uploadFeedArtwork).toHaveBeenCalledWith(file))
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'podcasts.feedSettings.artworkUploaded' }))
    )
    expect(await screen.findByRole('img', { name: 'podcasts.feedSettings.artworkAlt' })).toBeInTheDocument()
    expect(screen.queryByText('podcasts.feedSettings.noArtwork')).toBeNull()
  })

  it("shows the server's reason when it refuses the image, and keeps the current preview", async () => {
    getFeedSettings.mockResolvedValue({ ...SAVED, has_artwork: true, artwork_version: 'v1' })
    uploadFeedArtwork.mockRejectedValue(
      httpError(400, 'The artwork must be square (this one is 1400x1500 pixels).')
    )
    renderForm()
    await screen.findByRole('img', { name: 'podcasts.feedSettings.artworkAlt' })

    chooseFile(pngFile())

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith({
        title: 'podcasts.feedSettings.artworkUploadFailed',
        description: 'The artwork must be square (this one is 1400x1500 pixels).',
        variant: 'destructive',
      })
    )
    expect(screen.getByRole('img', { name: 'podcasts.feedSettings.artworkAlt' })).toBeInTheDocument()
  })

  it('turns away a file that is not a PNG or JPEG without uploading it', async () => {
    renderForm()
    await screen.findByText('podcasts.feedSettings.noArtwork')

    chooseFile(pngFile('cover.gif', 'image/gif'))

    expect(await screen.findByText('podcasts.feedSettings.artworkWrongType')).toBeInTheDocument()
    expect(uploadFeedArtwork).not.toHaveBeenCalled()
  })

  it('turns away a file over 10 MB without uploading it', async () => {
    renderForm()
    await screen.findByText('podcasts.feedSettings.noArtwork')

    chooseFile(pngFile('big.png', 'image/png', 10 * 1024 * 1024 + 1))

    expect(await screen.findByText('podcasts.feedSettings.artworkTooBig')).toBeInTheDocument()
    expect(uploadFeedArtwork).not.toHaveBeenCalled()
  })

  it('accepts a JPEG and a file of exactly 10 MB', async () => {
    uploadFeedArtwork.mockResolvedValue({ ...SAVED, has_artwork: true, artwork_version: 'v2' })
    renderForm()
    await screen.findByText('podcasts.feedSettings.noArtwork')

    chooseFile(pngFile('cover.jpg', 'image/jpeg', 10 * 1024 * 1024))

    await waitFor(() => expect(uploadFeedArtwork).toHaveBeenCalledTimes(1))
  })

  it('clears an earlier file-check message when a good file is chosen', async () => {
    uploadFeedArtwork.mockResolvedValue({ ...SAVED, has_artwork: true, artwork_version: 'v2' })
    renderForm()
    await screen.findByText('podcasts.feedSettings.noArtwork')
    chooseFile(pngFile('cover.gif', 'image/gif'))
    await screen.findByText('podcasts.feedSettings.artworkWrongType')

    chooseFile(pngFile())

    await waitFor(() => expect(screen.queryByText('podcasts.feedSettings.artworkWrongType')).toBeNull())
  })
})
