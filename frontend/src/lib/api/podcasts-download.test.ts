import { describe, expect, it } from 'vitest'

import { episodeDownloadFilename } from './podcasts'

describe('episodeDownloadFilename', () => {
  it('uses the episode name and the source file extension', () => {
    expect(episodeDownloadFilename('My Episode', 'episodes/abc/audio/abc.mp3')).toBe('My Episode.mp3')
    expect(episodeDownloadFilename('Clip', 'audio/clip.WAV?x=1')).toBe('Clip.wav')
  })

  it('strips characters that are unsafe in file names', () => {
    expect(episodeDownloadFilename('a/b:c*d?  "e"', null)).toBe('a b c d e.mp3')
  })

  it('falls back to a default name and mp3', () => {
    expect(episodeDownloadFilename('', undefined)).toBe('podcast-episode.mp3')
    expect(episodeDownloadFilename(null)).toBe('podcast-episode.mp3')
  })
})
