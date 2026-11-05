import apiClient from './client'
import { getApiUrl } from '@/lib/config'
import {
  PodcastEpisode,
  EpisodeProfile,
  SpeakerProfile,
  Language,
  PodcastGenerationRequest,
  PodcastGenerationResponse,
  ScriptPodcastRequest,
} from '@/lib/types/podcasts'

export type EpisodeProfileInput = Omit<EpisodeProfile, 'id'>
export type SpeakerProfileInput = Omit<SpeakerProfile, 'id'>

export async function resolvePodcastAssetUrl(path?: string | null): Promise<string | undefined> {
  if (!path) {
    return undefined
  }

  if (/^https?:\/\//i.test(path)) {
    return path
  }

  const base = await getApiUrl()

  if (path.startsWith('/')) {
    return `${base}${path}`
  }

  return `${base}/${path}`
}

/** File name for a downloaded episode: the episode name, made filesystem-safe. */
export function episodeDownloadFilename(name: string | null | undefined, sourcePath?: string | null): string {
  const extMatch = sourcePath?.split('?')[0].match(/\.([a-z0-9]{2,5})$/i)
  const ext = extMatch ? extMatch[1].toLowerCase() : 'mp3'
  const base = (name ?? '')
    .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 120)
  return `${base || 'podcast-episode'}.${ext}`
}

/**
 * Saves an episode's audio to the browser's downloads folder. The audio
 * endpoint is protected, so it is fetched through apiClient (auth header)
 * and handed to the browser as a blob.
 */
export async function downloadEpisodeAudio(
  episode: Pick<PodcastEpisode, 'name' | 'audio_url' | 'audio_file'>
): Promise<void> {
  const url = await resolvePodcastAssetUrl(episode.audio_url ?? episode.audio_file)
  if (!url) {
    throw new Error('Episode has no audio')
  }
  const response = await apiClient.get<Blob>(url, { responseType: 'blob' })
  const blobUrl = URL.createObjectURL(response.data)
  try {
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = episodeDownloadFilename(episode.name, episode.audio_file)
    document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    // Give the browser a moment to start the download before revoking.
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
  }
}

export const podcastsApi = {
  listEpisodes: async (params?: { notebook_id?: string }) => {
    const response = await apiClient.get<PodcastEpisode[]>('/podcasts/episodes', {
      params: params?.notebook_id ? { notebook_id: params.notebook_id } : undefined,
    })
    return response.data
  },

  deleteEpisode: async (episodeId: string) => {
    await apiClient.delete(`/podcasts/episodes/${episodeId}`)
  },

  retryEpisode: async (episodeId: string) => {
    const response = await apiClient.post<{ job_id: string; message: string }>(
      `/podcasts/episodes/${episodeId}/retry`
    )
    return response.data
  },

  listEpisodeProfiles: async () => {
    const response = await apiClient.get<EpisodeProfile[]>('/episode-profiles')
    return response.data
  },

  createEpisodeProfile: async (payload: EpisodeProfileInput) => {
    const response = await apiClient.post<EpisodeProfile>(
      '/episode-profiles',
      payload
    )
    return response.data
  },

  updateEpisodeProfile: async (profileId: string, payload: EpisodeProfileInput) => {
    const response = await apiClient.put<EpisodeProfile>(
      `/episode-profiles/${profileId}`,
      payload
    )
    return response.data
  },

  deleteEpisodeProfile: async (profileId: string) => {
    await apiClient.delete(`/episode-profiles/${profileId}`)
  },

  duplicateEpisodeProfile: async (profileId: string) => {
    const response = await apiClient.post<EpisodeProfile>(
      `/episode-profiles/${profileId}/duplicate`
    )
    return response.data
  },

  listSpeakerProfiles: async () => {
    const response = await apiClient.get<SpeakerProfile[]>('/speaker-profiles')
    return response.data
  },

  createSpeakerProfile: async (payload: SpeakerProfileInput) => {
    const response = await apiClient.post<SpeakerProfile>(
      '/speaker-profiles',
      payload
    )
    return response.data
  },

  updateSpeakerProfile: async (profileId: string, payload: SpeakerProfileInput) => {
    const response = await apiClient.put<SpeakerProfile>(
      `/speaker-profiles/${profileId}`,
      payload
    )
    return response.data
  },

  deleteSpeakerProfile: async (profileId: string) => {
    await apiClient.delete(`/speaker-profiles/${profileId}`)
  },

  duplicateSpeakerProfile: async (profileId: string) => {
    const response = await apiClient.post<SpeakerProfile>(
      `/speaker-profiles/${profileId}/duplicate`
    )
    return response.data
  },

  generatePodcast: async (payload: PodcastGenerationRequest) => {
    const response = await apiClient.post<PodcastGenerationResponse>(
      '/podcasts/generate',
      payload
    )
    return response.data
  },

  readScriptPodcast: async (payload: ScriptPodcastRequest) => {
    const response = await apiClient.post<PodcastGenerationResponse>(
      '/podcasts/read-script',
      payload
    )
    return response.data
  },

  listLanguages: async () => {
    const response = await apiClient.get<Language[]>('/languages')
    return response.data
  },
}
