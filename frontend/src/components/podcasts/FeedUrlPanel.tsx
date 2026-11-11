'use client'

import { useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { AlertTriangle, Check, Copy, Loader2, RefreshCcw, Rss } from 'lucide-react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { usePodcastFeedUrl, useRotatePodcastFeedToken } from '@/lib/hooks/use-podcasts'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'

/**
 * The private Podcast Feed URL for podcast apps ("Follow a Show by URL"), with
 * copy and rotate. Holding the URL is the only credential, so rotating it is
 * the remedy for a leak and breaks every existing subscription.
 */
export function FeedUrlPanel() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { data, isLoading, error } = usePodcastFeedUrl()
  const rotate = useRotatePodcastFeedToken()
  const [copied, setCopied] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current)
    },
    []
  )

  const handleCopy = async () => {
    if (!data) return
    try {
      await navigator.clipboard.writeText(data.feed_url)
      setCopied(true)
      if (resetTimer.current) clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be refused; leave the text selected to copy by hand.
      inputRef.current?.select()
      toast({ title: t('common.error'), variant: 'destructive' })
    }
  }

  // 422 = the server has no HTTPS address to put in the URL (see the Podcast Feed ADR).
  const needsHttps = isAxiosError(error) && error.response?.status === 422

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Rss className="h-4 w-4" />
          {t('podcasts.feed.title')}
        </CardTitle>
        <CardDescription>{t('podcasts.feed.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : needsHttps ? (
          <Alert className="bg-warn-tint text-warn border-warn/30">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>{t('podcasts.feed.needsHttpsTitle')}</AlertTitle>
            <AlertDescription>{t('podcasts.feed.needsHttpsDesc')}</AlertDescription>
          </Alert>
        ) : error || !data ? (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{t('podcasts.feed.loadFailed')}</AlertDescription>
          </Alert>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <Input
                ref={inputRef}
                readOnly
                value={data.feed_url}
                aria-label={t('podcasts.feed.urlLabel')}
                onFocus={(event) => event.currentTarget.select()}
                className="font-mono text-xs"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleCopy}
                aria-label={t('podcasts.feed.copy')}
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button type="button" variant="outline" disabled={rotate.isPending}>
                    <RefreshCcw className="mr-2 h-4 w-4" />
                    {rotate.isPending ? t('podcasts.feed.rotating') : t('podcasts.feed.rotate')}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t('podcasts.feed.rotateTitle')}</AlertDialogTitle>
                    <AlertDialogDescription>{t('podcasts.feed.rotateWarning')}</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                    <AlertDialogAction onClick={() => rotate.mutate()}>
                      {t('podcasts.feed.rotateConfirm')}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
            {copied ? (
              <p role="status" className="text-xs text-muted-foreground">
                {t('podcasts.feed.copied')}
              </p>
            ) : null}
            <p className="text-sm text-muted-foreground">{t('podcasts.feed.howTo')}</p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
