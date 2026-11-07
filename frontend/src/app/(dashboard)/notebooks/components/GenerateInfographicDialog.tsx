'use client'

import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  DEFAULT_INFOGRAPHIC_ASPECT,
  DEFAULT_INFOGRAPHIC_LAYOUT,
  DEFAULT_INFOGRAPHIC_STYLE,
  INFOGRAPHIC_ASPECTS,
  INFOGRAPHIC_LAYOUTS,
  INFOGRAPHIC_STYLES,
} from '@/lib/infographic-options'
import type { CreateInfographicRequest, InfographicAspect } from '@/lib/types/api'
import { cn } from '@/lib/utils'

const MAX_FOCUS_CHARS = 2000

interface GenerateInfographicDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** False when the notebook has no sources yet. */
  hasSources?: boolean
  isStarting?: boolean
  onGenerate: (data: CreateInfographicRequest) => Promise<unknown>
}

/** Pick a style, layout and shape (plus an optional focus) for a new infographic. */
export function GenerateInfographicDialog({
  open,
  onOpenChange,
  hasSources = true,
  isStarting = false,
  onGenerate,
}: GenerateInfographicDialogProps) {
  const { t } = useTranslation()
  const [style, setStyle] = useState(DEFAULT_INFOGRAPHIC_STYLE)
  const [layout, setLayout] = useState(DEFAULT_INFOGRAPHIC_LAYOUT)
  const [aspect, setAspect] = useState<InfographicAspect>(DEFAULT_INFOGRAPHIC_ASPECT)
  const [focus, setFocus] = useState('')

  useEffect(() => {
    if (!open) {
      setStyle(DEFAULT_INFOGRAPHIC_STYLE)
      setLayout(DEFAULT_INFOGRAPHIC_LAYOUT)
      setAspect(DEFAULT_INFOGRAPHIC_ASPECT)
      setFocus('')
    }
  }, [open])

  const canSubmit = hasSources && !isStarting

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    try {
      const instructions = focus.trim()
      await onGenerate({ style, layout, aspect, ...(instructions ? { instructions } : {}) })
      onOpenChange(false)
    } catch {
      // The hook shows the error toast; keep the dialog open.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col sm:max-w-[680px]">
        <DialogHeader>
          <DialogTitle>{t('infographic.dialogTitle')}</DialogTitle>
          <DialogDescription>{t('infographic.dialogDesc')}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col gap-4">
          <div className="-mx-1 min-h-0 flex-1 space-y-4 overflow-y-auto px-1">
            <div className="space-y-2">
              <Label id="infographic-style-label">{t('infographic.styleLabel')}</Label>
              <div
                role="radiogroup"
                aria-labelledby="infographic-style-label"
                className="grid grid-cols-2 gap-2 sm:grid-cols-3"
              >
                {INFOGRAPHIC_STYLES.map((option) => {
                  const selected = style === option.id
                  const [paper, ink, accent] = option.swatch
                  return (
                    <button
                      key={option.id}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      disabled={isStarting}
                      onClick={() => setStyle(option.id)}
                      data-testid={`infographic-style-${option.id}`}
                      className={cn(
                        'flex min-w-0 items-start gap-2 rounded-lg border p-2 text-left transition-colors',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        'disabled:cursor-not-allowed disabled:opacity-60',
                        selected ? 'border-teal bg-teal-tint' : 'hover:bg-accent/50'
                      )}
                    >
                      {/* A preview of the style's own palette, not app chrome. */}
                      <span
                        aria-hidden
                        className="mt-0.5 flex h-8 w-8 shrink-0 items-end gap-0.5 overflow-hidden rounded border p-1"
                        style={{ background: paper }}
                      >
                        <span className="h-3 w-2 rounded-sm" style={{ background: ink }} />
                        <span className="h-5 w-2 rounded-sm" style={{ background: accent }} />
                        <span className="h-2 w-2 rounded-sm" style={{ background: ink }} />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">{t(option.labelKey)}</span>
                        <span className="line-clamp-2 text-xs text-muted-foreground">{t(option.descKey)}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="infographic-layout">{t('infographic.layoutLabel')}</Label>
                <Select value={layout} onValueChange={setLayout} disabled={isStarting}>
                  <SelectTrigger id="infographic-layout" data-testid="infographic-layout">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {INFOGRAPHIC_LAYOUTS.map((option) => (
                      <SelectItem key={option.id} value={option.id}>
                        {t(option.labelKey)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label id="infographic-aspect-label">{t('infographic.aspectLabel')}</Label>
                <div role="radiogroup" aria-labelledby="infographic-aspect-label" className="grid grid-cols-3 gap-1">
                  {INFOGRAPHIC_ASPECTS.map((option) => {
                    const selected = aspect === option.id
                    return (
                      <button
                        key={option.id}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        disabled={isStarting}
                        onClick={() => setAspect(option.id)}
                        data-testid={`infographic-aspect-${option.id}`}
                        className={cn(
                          'h-9 rounded-md border px-2 text-xs font-medium transition-colors',
                          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                          selected ? 'border-teal bg-teal-tint' : 'hover:bg-accent/50'
                        )}
                      >
                        {t(option.labelKey)}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>

            {!hasSources && (
              <p role="alert" className="text-sm text-destructive">
                {t('explainer.noSources')}
              </p>
            )}

            <div className="space-y-2">
              <Label htmlFor="infographic-focus">{t('infographic.focusLabel')}</Label>
              <Textarea
                id="infographic-focus"
                value={focus}
                onChange={(event) => setFocus(event.target.value.slice(0, MAX_FOCUS_CHARS))}
                placeholder={t('infographic.focusPlaceholder')}
                rows={3}
                disabled={isStarting}
              />
              <p className="text-xs text-muted-foreground">{t('infographic.timeHint')}</p>
            </div>
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
