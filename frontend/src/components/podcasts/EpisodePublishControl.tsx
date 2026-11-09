'use client'

import { useState } from 'react'
import { Rss } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { usePublishPodcastEpisode, useUnpublishPodcastEpisode } from '@/lib/hooks/use-podcasts'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { PodcastEpisode } from '@/lib/types/podcasts'

// Mirror the server (open_notebook/podcasts/publishing.py): the default
// description length and the longest summary it accepts.
const SUMMARY_EXCERPT_CHARS = 300
const SUMMARY_MAX_CHARS = 4000

/** Plain-text description from the outline's segments, as the server builds it. */
function defaultSummary(episode: PodcastEpisode): string {
  const segments = (episode.outline as { segments?: Array<{ description?: unknown }> } | null | undefined)
    ?.segments
  const parts = (Array.isArray(segments) ? segments : [])
    .map((segment) => String(segment?.description ?? '').split(/\s+/).filter(Boolean).join(' '))
    .filter(Boolean)
  const text = parts.join(' ') || episode.name
  if (text.length <= SUMMARY_EXCERPT_CHARS) return text

  let cut = text.slice(0, SUMMARY_EXCERPT_CHARS - 1)
  if (!/\s/.test(text[SUMMARY_EXCERPT_CHARS - 1]) && cut.includes(' ')) {
    cut = cut.slice(0, cut.lastIndexOf(' '))
  }
  return `${cut.trimEnd()}…`
}

/**
 * Publish / Unpublish for one episode in the Podcast Feed (see CONTEXT.md).
 * Offered for completed episodes with audio; a published episode always shows
 * its state and Unpublish, so a broken one can still be pulled.
 */
export function EpisodePublishControl({ episode }: { episode: PodcastEpisode }) {
  const { t } = useTranslation()
  const publish = usePublishPodcastEpisode()
  const unpublish = useUnpublishPodcastEpisode()
  const [open, setOpen] = useState(false)
  const [summary, setSummary] = useState('')

  const published = !!episode.published_at
  const publishable = episode.job_status === 'completed' && !!(episode.audio_url || episode.audio_file)

  if (published) {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="border-fern/30 bg-fern-tint text-xs text-fern">
          <Rss className="mr-1 h-3 w-3" />
          {t('podcasts.feed.inFeed')}
        </Badge>
        <Button
          variant="outline"
          size="sm"
          disabled={unpublish.isPending}
          onClick={() => unpublish.mutate(episode.id)}
        >
          {unpublish.isPending ? t('podcasts.feed.unpublishing') : t('podcasts.feed.unpublish')}
        </Button>
      </div>
    )
  }

  if (!publishable) return null

  const tooLong = summary.trim().length > SUMMARY_MAX_CHARS

  const openDialog = () => {
    setSummary(defaultSummary(episode))
    setOpen(true)
  }

  const confirm = () => {
    publish.mutate({ episodeId: episode.id, summary: summary.trim() }, { onSuccess: () => setOpen(false) })
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={openDialog}>
        <Rss className="mr-2 h-4 w-4" />
        {t('podcasts.feed.publish')}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('podcasts.feed.publishTitle')}</DialogTitle>
            <DialogDescription>{t('podcasts.feed.publishDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor={`feed-summary-${episode.id}`}>{t('podcasts.feed.summaryLabel')}</Label>
            <Textarea
              id={`feed-summary-${episode.id}`}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              rows={6}
              aria-invalid={tooLong}
            />
            {tooLong ? (
              <p role="alert" className="text-xs text-destructive">
                {t('podcasts.feed.summaryTooLong')}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={confirm} disabled={tooLong || publish.isPending}>
              {publish.isPending ? t('podcasts.feed.publishing') : t('podcasts.feed.publishConfirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
