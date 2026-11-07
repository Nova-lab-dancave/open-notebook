'use client'

import { useEffect, useState } from 'react'
import { Download, ImageDown, Maximize2, Minimize2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { notesApi } from '@/lib/api/notes'
import { useNote } from '@/lib/hooks/use-notes'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { NoteResponse } from '@/lib/types/api'
import {
  formatFileSize,
  noteFileKind,
  saveBlob,
  saveNoteFile,
  svgToPng,
  withExtension,
} from '@/lib/utils/note-files'
import { cn } from '@/lib/utils'

interface NoteFileViewerProps {
  note: NoteResponse | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Pop-up viewer for a note created from a file. PDFs and HTML show the original
 * (fetched with auth into a blob so the request carries the token); DOCX, text
 * and Markdown show the text extracted from the file. HTML is rendered in a
 * fully sandboxed iframe, so scripts in the file can never run. Generated
 * explainers are the one exception: their scripts run (sandbox `allow-scripts`
 * without `allow-same-origin`, so an opaque origin with no access to the app),
 * the server-injected CSP blocks subresource requests, and the app's
 * `frame-src` policy (next.config.ts) stops the frame navigating to an outside
 * URL (ADR-015). Explainers are not offered for download: a copy opened from
 * disk would run outside the sandbox.
 *
 * Generated infographics (sanitised SVG, ADR-016) open full page as an `<img>`,
 * where SVG can never run scripts, and download as SVG or PNG.
 */
export function NoteFileViewer({ note, open, onOpenChange }: NoteFileViewerProps) {
  const { t } = useTranslation()
  const attachment = note?.attachment ?? null
  const kind = attachment ? noteFileKind(attachment.type) : null
  const isInfographic = kind === 'svg' && !!note?.infographic
  const showsOriginal = kind === 'pdf' || kind === 'html' || isInfographic
  const isExplainer = kind === 'html' && !!note?.explainer
  const [actualSize, setActualSize] = useState(false)
  const [exporting, setExporting] = useState(false)

  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const noteId = note?.id
  const attachmentType = attachment?.type

  useEffect(() => {
    if (!open || !noteId || !attachmentType || !showsOriginal) return
    let cancelled = false
    let url: string | null = null
    setBlobUrl(null)
    setFailed(false)
    setActualSize(false)
    notesApi
      .fetchFile(noteId)
      .then((data) => {
        if (cancelled) return
        // Force the type we expect rather than trusting the response.
        url = URL.createObjectURL(new Blob([data], { type: attachmentType }))
        setBlobUrl(url)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [open, noteId, attachmentType, showsOriginal])

  const { data: fullNote, isError: textFailed } = useNote(noteId, {
    enabled: open && !!attachment && !showsOriginal,
  })

  const handleDownload = async () => {
    if (!note || !attachment) return
    try {
      await saveNoteFile(note.id, attachment.name, attachment.type)
    } catch {
      setFailed(true)
    }
  }

  const handleDownloadPng = async () => {
    if (!note || !attachment) return
    setExporting(true)
    try {
      const png = await svgToPng(await notesApi.fetchFile(note.id))
      saveBlob(png, withExtension(attachment.name, '.png'))
    } catch {
      setFailed(true)
    } finally {
      setExporting(false)
    }
  }

  if (!note || !attachment) return null

  if (isInfographic) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          className="flex h-[100dvh] w-screen max-w-none flex-col gap-3 rounded-none border-0 p-3 sm:max-w-none sm:p-4"
          data-testid="infographic-viewer"
        >
          <DialogHeader className="pr-8">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <DialogTitle className="min-w-0 truncate">{note.title || attachment.name}</DialogTitle>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActualSize((value) => !value)}
                  aria-pressed={actualSize}
                  title={actualSize ? t('infographic.fitToScreen') : t('infographic.actualSize')}
                >
                  {actualSize ? <Minimize2 className="mr-2 h-4 w-4" /> : <Maximize2 className="mr-2 h-4 w-4" />}
                  {actualSize ? t('infographic.fitToScreen') : t('infographic.actualSize')}
                </Button>
                <Button variant="outline" size="sm" onClick={handleDownload}>
                  <Download className="mr-2 h-4 w-4" />
                  {t('infographic.downloadSvg')}
                </Button>
                <Button variant="outline" size="sm" onClick={() => void handleDownloadPng()} disabled={exporting}>
                  <ImageDown className="mr-2 h-4 w-4" />
                  {t('infographic.downloadPng')}
                </Button>
              </div>
            </div>
            <DialogDescription>
              {t('infographic.viewerMeta', { size: formatFileSize(attachment.size) })}
            </DialogDescription>
          </DialogHeader>

          <div className={cn('min-h-0 flex-1 rounded-md border bg-muted', actualSize ? 'overflow-auto' : 'overflow-hidden')}>
            {failed ? (
              <p role="alert" className="p-6 text-sm text-destructive">
                {t('noteFiles.loadFailed')}
              </p>
            ) : blobUrl ? (
              // eslint-disable-next-line @next/next/no-img-element -- a local blob URL, not an optimisable asset
              <img
                src={blobUrl}
                alt={note.title || attachment.name}
                onClick={() => setActualSize((value) => !value)}
                className={cn(
                  'mx-auto block',
                  actualSize ? 'max-w-none cursor-zoom-out' : 'h-full w-full cursor-zoom-in object-contain'
                )}
              />
            ) : (
              <div className="flex h-full items-center justify-center">
                <LoadingSpinner />
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] max-w-5xl flex-col gap-3">
        <DialogHeader className="pr-8">
          <div className="flex items-center justify-between gap-3">
            <DialogTitle className="truncate">
              {isExplainer ? note.title || attachment.name : attachment.name}
            </DialogTitle>
            {!isExplainer && (
              <Button variant="outline" size="sm" onClick={handleDownload}>
                <Download className="mr-2 h-4 w-4" />
                {t('noteFiles.download')}
              </Button>
            )}
          </div>
          <DialogDescription>
            {isExplainer
              ? t('explainer.viewerMeta', { size: formatFileSize(attachment.size) })
              : t('noteFiles.meta', { size: formatFileSize(attachment.size) })}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-hidden rounded-md border bg-card">
          {failed || textFailed ? (
            <p role="alert" className="p-6 text-sm text-destructive">
              {t('noteFiles.loadFailed')}
            </p>
          ) : showsOriginal ? (
            blobUrl ? (
              <iframe
                src={blobUrl}
                title={attachment.name}
                // Empty sandbox: no scripts, no same-origin access. Not applied to PDFs
                // because browsers refuse to show their built-in PDF viewer in a sandbox
                // (a PDF cannot run page scripts in our origin).
                {...(kind === 'html' ? { sandbox: isExplainer ? 'allow-scripts' : '' } : {})}
                className={isExplainer ? 'h-full w-full bg-background' : 'h-full w-full bg-white'}
              />
            ) : (
              <div className="flex h-full items-center justify-center">
                <LoadingSpinner />
              </div>
            )
          ) : fullNote ? (
            <div className="h-full overflow-y-auto p-6">
              <div className="prose prose-sm dark:prose-invert max-w-none break-words">
                <MarkdownRenderer>{fullNote.content ?? ''}</MarkdownRenderer>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center">
              <LoadingSpinner />
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
