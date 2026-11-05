'use client'

import type { TFunction } from 'i18next'
import {
  Book,
  Search,
  Mic,
  Bot,
  Shuffle,
  Settings,
  FileText,
  Wrench,
} from 'lucide-react'

import { cn } from '@/lib/utils'

/** The app's main navigation, shared by the desktop sidebar and the mobile menu. */
export const getNavigation = (t: TFunction) => [
  {
    title: t('navigation.collect'),
    items: [
      { name: t('navigation.sources'), href: '/sources', icon: FileText, iconClass: 'text-sage' },
    ],
  },
  {
    title: t('navigation.process'),
    items: [
      { name: t('navigation.notebooks'), href: '/notebooks', icon: Book, iconClass: 'text-teal' },
      { name: t('navigation.askAndSearch'), href: '/search', icon: Search, iconClass: undefined },
    ],
  },
  {
    title: t('navigation.create'),
    items: [
      { name: t('navigation.podcasts'), href: '/podcasts', icon: Mic, iconClass: 'text-mauve' },
    ],
  },
  {
    title: t('navigation.manage'),
    items: [
      { name: t('navigation.models'), href: '/settings/models', icon: Bot, iconClass: undefined },
      { name: t('navigation.transformations'), href: '/transformations', icon: Shuffle, iconClass: undefined },
      { name: t('navigation.settings'), href: '/settings', icon: Settings, iconClass: undefined },
      { name: t('navigation.advanced'), href: '/advanced', icon: Wrench, iconClass: undefined },
    ],
  },
] as const

export type Navigation = ReturnType<typeof getNavigation>

/**
 * The active item is the longest href that prefixes the current path.
 * Longest-wins keeps `/settings` from also highlighting on `/settings/models`
 * (the Models page is a URL child of the Settings page but a distinct item).
 */
export function getActiveHref(navigation: Navigation, pathname: string | null): string | undefined {
  return navigation
    .map((section) => section.items)
    .flat()
    .filter((item) => pathname === item.href || pathname?.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href
}

// The tri-hue mark recomposed in the owned palette: fern / gold / teal.
export function LogoPebbles({ className }: { className?: string }) {
  return (
    <span className={cn('flex items-center gap-[3px]', className)} aria-hidden="true">
      <span className="size-[9px] rounded-[3px] bg-fern" />
      <span className="size-[9px] rounded-[3px] bg-gold" />
      <span className="size-[9px] rounded-[3px] bg-teal" />
    </span>
  )
}
