'use client'

import { formatDistanceToNow } from 'date-fns'
import { Bot, Download, FileText, MoreVertical, Presentation, StickyNote, Trash2, User } from 'lucide-react'

import { ContextToggle } from '@/components/common/ContextToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { NoteResponse } from '@/lib/types/api'
import { getDateLocale } from '@/lib/utils/date-locale'
import { formatFileSize } from '@/lib/utils/note-files'
import type { NoteContextMode } from '../[id]/page'

/**
 * Grid for the notes pane: as many square cards per row as fit, each at least
 * 10rem wide, scaling up to fill the row.
 */
export const NOTE_GRID_CLASS = 'grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-3'

/** Shared frame for every square card in the notes grid. */
export const NOTE_CARD_CLASS = 'relative flex aspect-square min-w-0 flex-col overflow-hidden rounded-md border p-3'

interface NoteCardProps {
  note: NoteResponse
  contextMode?: NoteContextMode
  onContextModeChange?: (mode: NoteContextMode) => void
  onOpen: (note: NoteResponse) => void
  onDelete: (noteId: string) => void
  onDownload: (note: NoteResponse) => void
}

/** One note, file or explainer as a square card in the notes grid. */
export function NoteCard({
  note,
  contextMode,
  onContextModeChange,
  onOpen,
  onDelete,
  onDownload,
}: NoteCardProps) {
  const { t, language } = useTranslation()
  const isExplainer = !!note.attachment && !!note.explainer
  // The notebook notes list omits note bodies, so most cards have no text
  // preview: they show their type as a large icon instead (thumbnails later).
  const [PreviewIcon, previewColor] = isExplainer
    ? [Presentation, 'text-teal']
    : note.attachment
      ? [FileText, 'text-sage']
      : note.note_type === 'ai'
        ? [Bot, 'text-teal']
        : [StickyNote, 'text-muted-foreground']

  return (
    <div
      className={`${NOTE_CARD_CLASS} group cursor-pointer bg-card shadow-none card-hover`}
      onClick={() => onOpen(note)}
      data-testid="note-card"
    >
      <div className="flex items-start justify-between gap-1">
        <div className="flex min-w-0 items-center gap-1.5">
          {isExplainer ? (
            <>
              <Presentation className="h-4 w-4 shrink-0 text-teal" />
              <Badge variant="secondary" className="truncate text-xs">
                {t('explainer.badge')}
              </Badge>
            </>
          ) : note.attachment ? (
            <>
              <FileText className="h-4 w-4 shrink-0 text-sage" />
              <Badge variant="secondary" className="truncate text-xs uppercase">
                {note.attachment.name.split('.').pop()}
              </Badge>
            </>
          ) : (
            <>
              {note.note_type === 'ai' ? (
                <Bot className="h-4 w-4 shrink-0 text-teal" />
              ) : (
                <User className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <Badge variant="secondary" className="truncate text-xs">
                {note.note_type === 'ai' ? t('common.aiGenerated') : t('common.human')}
              </Badge>
            </>
          )}
        </div>

        <div className="-mr-1.5 -mt-1.5 flex shrink-0 items-center">
          {onContextModeChange && contextMode && (
            <div onClick={(event) => event.stopPropagation()}>
              <ContextToggle
                mode={contextMode}
                hasInsights={false}
                onChange={onContextModeChange}
              />
            </div>
          )}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
                onClick={(e) => e.stopPropagation()}
                aria-label={t('common.actions')}
              >
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {note.attachment && !note.explainer && (
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    onDownload(note)
                  }}
                >
                  <Download className="h-4 w-4 mr-2" />
                  {t('noteFiles.download')}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(note.id)
                }}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                {t('notebooks.deleteNote')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {note.title && (
        <h4
          className="mt-2 line-clamp-2 text-sm font-medium leading-snug [overflow-wrap:anywhere]"
          title={note.title}
        >
          {note.title}
        </h4>
      )}

      <div className="mt-1 min-h-0 flex-1 overflow-hidden">
        {note.content ? (
          <p className="line-clamp-4 text-xs text-muted-foreground [overflow-wrap:anywhere]">
            {note.content}
          </p>
        ) : (
          <div className="flex h-full items-center justify-center" aria-hidden>
            <PreviewIcon className={`h-10 max-h-full w-10 opacity-40 ${previewColor}`} />
          </div>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="truncate">
          {formatDistanceToNow(new Date(note.updated), {
            addSuffix: true,
            locale: getDateLocale(language),
          })}
        </span>
        {note.attachment && (
          <span className="shrink-0">{formatFileSize(note.attachment.size)}</span>
        )}
      </div>
    </div>
  )
}
