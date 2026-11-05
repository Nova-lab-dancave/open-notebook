'use client'

import { useEffect, useState } from 'react'
import { BookOpen, FolderGit2, Globe, Loader2, type LucideIcon } from 'lucide-react'

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
import { useTranslation } from '@/lib/hooks/use-translation'
import type { CreateExplainerRequest, ExplainerMode } from '@/lib/types/api'
import { cn } from '@/lib/utils'

const MAX_FOCUS_CHARS = 2000

interface ExplainerOption {
  mode: ExplainerMode
  icon: LucideIcon
  titleKey: string
  descKey: string
  available: boolean
}

// Order and availability follow the plan in issue #19: only "sources" is built so far.
const OPTIONS: ExplainerOption[] = [
  { mode: 'sources', icon: BookOpen, titleKey: 'explainer.optionSourcesTitle', descKey: 'explainer.optionSourcesDesc', available: true },
  { mode: 'repo', icon: FolderGit2, titleKey: 'explainer.optionRepoTitle', descKey: 'explainer.optionRepoDesc', available: false },
  { mode: 'discover', icon: Globe, titleKey: 'explainer.optionDiscoverTitle', descKey: 'explainer.optionDiscoverDesc', available: false },
]

interface GenerateExplainerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** False when the notebook has no sources yet ("from sources" can't run). */
  hasSources?: boolean
  isStarting?: boolean
  onGenerate: (data: CreateExplainerRequest) => Promise<unknown>
}

export function GenerateExplainerDialog({
  open,
  onOpenChange,
  hasSources = true,
  isStarting = false,
  onGenerate,
}: GenerateExplainerDialogProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<ExplainerMode>('sources')
  const [focus, setFocus] = useState('')

  useEffect(() => {
    if (!open) {
      setMode('sources')
      setFocus('')
    }
  }, [open])

  const canSubmit = mode === 'sources' && hasSources && !isStarting

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    try {
      const instructions = focus.trim()
      await onGenerate({ mode: 'sources', ...(instructions ? { instructions } : {}) })
      onOpenChange(false)
    } catch {
      // The hook shows the error toast; keep the dialog open.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{t('explainer.dialogTitle')}</DialogTitle>
          <DialogDescription>{t('explainer.dialogDesc')}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div role="radiogroup" aria-label={t('explainer.dialogTitle')} className="grid gap-2">
            {OPTIONS.map((option) => {
              const Icon = option.icon
              const selected = mode === option.mode
              return (
                <button
                  key={option.mode}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  disabled={!option.available || isStarting}
                  onClick={() => setMode(option.mode)}
                  data-testid={`explainer-option-${option.mode}`}
                  className={cn(
                    'flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    'disabled:cursor-not-allowed disabled:opacity-60',
                    selected ? 'border-teal bg-teal-tint' : 'hover:bg-accent/50'
                  )}
                >
                  <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', selected ? 'text-teal' : 'text-muted-foreground')} aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2 text-sm font-medium">
                      {t(option.titleKey)}
                      {!option.available && (
                        <Badge variant="secondary" className="text-[10px] uppercase">
                          {t('explainer.comingSoon')}
                        </Badge>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">{t(option.descKey)}</span>
                  </span>
                </button>
              )
            })}
          </div>

          {mode === 'sources' && !hasSources && (
            <p role="alert" className="text-sm text-destructive">
              {t('explainer.noSources')}
            </p>
          )}

          <div className="space-y-2">
            <Label htmlFor="explainer-focus">{t('explainer.focusLabel')}</Label>
            <Textarea
              id="explainer-focus"
              value={focus}
              onChange={(event) => setFocus(event.target.value.slice(0, MAX_FOCUS_CHARS))}
              placeholder={t('explainer.focusPlaceholder')}
              rows={3}
              disabled={isStarting}
            />
            <p className="text-xs text-muted-foreground">{t('explainer.timeHint')}</p>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isStarting}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {isStarting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {isStarting ? t('explainer.starting') : t('explainer.submit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
