'use client'

import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, ImageIcon, Loader2, Upload } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  usePodcastFeedArtwork,
  usePodcastFeedSettings,
  useUpdatePodcastFeedSettings,
  useUploadPodcastFeedArtwork,
} from '@/lib/hooks/use-podcasts'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { PodcastFeedSettings, PodcastFeedSettingsUpdate } from '@/lib/types/podcasts'

// Quick checks before uploading. The server still checks everything (format by
// content, square, 1400-3000 px) and its reason is shown if it refuses.
const ARTWORK_TYPES = ['image/png', 'image/jpeg']
const ARTWORK_MAX_BYTES = 10 * 1024 * 1024

type TextField = keyof PodcastFeedSettingsUpdate
const TEXT_FIELDS: TextField[] = ['title', 'author', 'description', 'language']

function textValues(settings: PodcastFeedSettings): Record<TextField, string> {
  return {
    title: settings.title,
    author: settings.author,
    description: settings.description,
    language: settings.language,
  }
}

function ArtworkPreview({ settings }: { settings: PodcastFeedSettings }) {
  const { t } = useTranslation()
  const artwork = usePodcastFeedArtwork(settings.artwork_version, settings.has_artwork)
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!artwork.data) {
      setUrl(null)
      return
    }
    const objectUrl = URL.createObjectURL(artwork.data)
    setUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [artwork.data])

  if (!settings.has_artwork) {
    return (
      <div className="flex h-24 w-24 flex-col items-center justify-center gap-1 rounded-md border border-dashed text-center text-xs text-muted-foreground">
        <ImageIcon className="h-5 w-5" />
        {t('podcasts.feedSettings.noArtwork')}
      </div>
    )
  }
  if (!url) {
    return (
      <div className="flex h-24 w-24 items-center justify-center rounded-md border">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    )
  }
  // eslint-disable-next-line @next/next/no-img-element -- a blob URL of an authenticated image
  return <img src={url} alt={t('podcasts.feedSettings.artworkAlt')} className="h-24 w-24 rounded-md border object-cover" />
}

function FeedSettingsFields({ settings }: { settings: PodcastFeedSettings }) {
  const { t } = useTranslation()
  const update = useUpdatePodcastFeedSettings()
  const upload = useUploadPodcastFeedArtwork()
  const [values, setValues] = useState(() => textValues(settings))
  const [fileError, setFileError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const saved = textValues(settings)
  const changes = Object.fromEntries(
    TEXT_FIELDS.filter((field) => values[field] !== saved[field]).map((field) => [field, values[field]])
  ) as PodcastFeedSettingsUpdate
  const dirty = Object.keys(changes).length > 0

  const handleSave = () => {
    // Blank fields are sent as-is; the server turns them back into the defaults,
    // so show the values it settled on.
    update.mutate(changes, { onSuccess: (result) => setValues(textValues(result)) })
  }

  const handleFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = '' // lets the same file be chosen again
    if (!file) return
    if (!ARTWORK_TYPES.includes(file.type)) {
      setFileError(t('podcasts.feedSettings.artworkWrongType'))
      return
    }
    if (file.size > ARTWORK_MAX_BYTES) {
      setFileError(t('podcasts.feedSettings.artworkTooBig'))
      return
    }
    setFileError(null)
    upload.mutate(file)
  }

  const set = (field: TextField) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setValues((current) => ({ ...current, [field]: event.target.value }))

  return (
    <CardContent className="space-y-6">
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="feed-title">{t('podcasts.feedSettings.titleLabel')}</Label>
          <Input id="feed-title" value={values.title} onChange={set('title')} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="feed-author">{t('podcasts.feedSettings.authorLabel')}</Label>
          <Input id="feed-author" value={values.author} onChange={set('author')} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="feed-description">{t('podcasts.feedSettings.descriptionLabel')}</Label>
          <Textarea id="feed-description" rows={3} value={values.description} onChange={set('description')} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="feed-language">{t('podcasts.feedSettings.languageLabel')}</Label>
          <Input id="feed-language" value={values.language} onChange={set('language')} className="max-w-40" />
          <p className="text-xs text-muted-foreground">{t('podcasts.feedSettings.languageHint')}</p>
        </div>
        <Button type="button" onClick={handleSave} disabled={!dirty || update.isPending}>
          {update.isPending ? t('podcasts.feedSettings.saving') : t('podcasts.feedSettings.save')}
        </Button>
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium">{t('podcasts.feedSettings.artworkLabel')}</p>
        <div className="flex items-center gap-4">
          <ArtworkPreview settings={settings} />
          <div className="space-y-2">
            <input
              ref={fileInput}
              type="file"
              accept="image/png,image/jpeg"
              className="hidden"
              aria-label={t('podcasts.feedSettings.chooseArtwork')}
              onChange={handleFile}
            />
            <Button
              type="button"
              variant="outline"
              disabled={upload.isPending}
              onClick={() => fileInput.current?.click()}
            >
              <Upload className="mr-2 h-4 w-4" />
              {upload.isPending
                ? t('podcasts.feedSettings.uploading')
                : settings.has_artwork
                  ? t('podcasts.feedSettings.replaceArtwork')
                  : t('podcasts.feedSettings.uploadArtwork')}
            </Button>
            <p className="text-xs text-muted-foreground">{t('podcasts.feedSettings.artworkHint')}</p>
            {fileError ? (
              <p role="alert" className="text-xs text-destructive">
                {fileError}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </CardContent>
  )
}

/** Show title, author, description, language and artwork of the Podcast Feed. */
export function FeedSettingsForm() {
  const { t } = useTranslation()
  const { data, isLoading, error } = usePodcastFeedSettings()

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('podcasts.feedSettings.title')}</CardTitle>
        <CardDescription>{t('podcasts.feedSettings.desc')}</CardDescription>
      </CardHeader>
      {isLoading ? (
        <CardContent>
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </CardContent>
      ) : error || !data ? (
        <CardContent>
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{t('podcasts.feedSettings.loadFailed')}</AlertDescription>
          </Alert>
        </CardContent>
      ) : (
        <FeedSettingsFields settings={data} />
      )}
    </Card>
  )
}
