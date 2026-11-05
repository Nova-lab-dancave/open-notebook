'use client'

import { Book, FileText, Mic } from 'lucide-react'

import { DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { useTranslation } from '@/lib/hooks/use-translation'

type CreateTarget = 'source' | 'notebook' | 'podcast'

interface CreateMenuItemsProps {
  /** Called after an item is picked, so the owner can close its menu. */
  onSelected: () => void
}

/**
 * The items of the "+ New" menu. The sidebar and the mobile bottom bar both
 * render these inside their own DropdownMenu, so both open the same dialogs.
 */
export function CreateMenuItems({ onSelected }: CreateMenuItemsProps) {
  const { t } = useTranslation()
  const { openSourceDialog, openNotebookDialog, openPodcastDialog } = useCreateDialogs()

  const items: { target: CreateTarget; label: string; icon: typeof FileText; open: () => void }[] = [
    { target: 'source', label: t('common.source'), icon: FileText, open: openSourceDialog },
    { target: 'notebook', label: t('common.notebook'), icon: Book, open: openNotebookDialog },
    { target: 'podcast', label: t('common.podcast'), icon: Mic, open: openPodcastDialog },
  ]

  return (
    <>
      {items.map(({ target, label, icon: Icon, open }) => (
        <DropdownMenuItem
          key={target}
          onSelect={(event) => {
            event.preventDefault()
            onSelected()
            open()
          }}
          className="gap-2"
        >
          <Icon className="h-4 w-4" />
          {label}
        </DropdownMenuItem>
      ))}
    </>
  )
}
