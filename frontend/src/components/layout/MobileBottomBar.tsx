'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { AudioLines, LogOut, Menu, Plus, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { LanguageToggle } from '@/components/common/LanguageToggle'
import { useAuth } from '@/lib/hooks/use-auth'
import { useTranslation } from '@/lib/hooks/use-translation'
import { CreateMenuItems } from './CreateMenuItems'
import { SidebarSections } from './SidebarSections'
import { getActiveHref, getNavigation, LogoPebbles } from './navigation'

/**
 * Route of the live meeting transcription page (#21). Meetings are not on
 * main yet, so the right-hand button renders disabled until this is set.
 * TODO(#21): set to the meeting page route once it lands.
 */
export const MEETING_ROUTE: string | null = null

/** Height of the bar itself (set in globals.css), without the home-indicator safe area. */
export const MOBILE_BAR_HEIGHT = 'var(--mobile-bar-height)'

/** The navigation that lives in the sidebar on desktop, as a bottom sheet. */
function MobileMenuSheet({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const pathname = usePathname()
  const { logout } = useAuth()
  const navigation = getNavigation(t)
  const activeHref = getActiveHref(navigation, pathname)
  const close = () => onOpenChange(false)

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 fixed inset-0 z-50 bg-black/35 backdrop-blur-sm" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          data-testid="mobile-menu-sheet"
          className="data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom fixed inset-x-0 bottom-0 z-50 flex max-h-[85dvh] flex-col glass-dock rounded-t-xl border-b-0 text-sidebar-foreground duration-200"
        >
          <div className="flex h-14 shrink-0 items-center justify-between px-4">
            <div className="flex items-center gap-2.5">
              <LogoPebbles />
              <DialogPrimitive.Title className="font-display text-[15px] font-bold tracking-tight">
                {t('common.appName')}
              </DialogPrimitive.Title>
            </div>
            <DialogPrimitive.Close asChild>
              <Button variant="ghost" size="icon" aria-label={t('common.close')}>
                <X className="h-4 w-4" />
              </Button>
            </DialogPrimitive.Close>
          </div>

          <nav
            aria-label={t('navigation.nav')}
            className="flex-1 space-y-1 overflow-y-auto px-3 pb-3"
            // Any link in the sheet (including notebook sections) navigates
            // away, so close the sheet on every link click.
            onClick={(event) => {
              if ((event.target as HTMLElement).closest('a')) close()
            }}
          >
            {navigation.map((section, index) => (
              <div key={section.title}>
                {index > 0 && <Separator className="my-3" />}
                <h3 className="mb-1.5 px-3 text-[10.5px] font-bold uppercase tracking-[0.14em] text-sidebar-foreground/40">
                  {section.title}
                </h3>
                <div className="space-y-1">
                  {section.items.map((item) => {
                    const isActive = item.href === activeHref
                    return (
                      <Link key={item.href} href={item.href}>
                        <Button
                          variant="ghost"
                          className={cn(
                            'h-11 w-full justify-start gap-2.5 text-[15px] font-medium text-sidebar-foreground/80 sidebar-menu-item',
                            isActive &&
                              'bg-popover font-semibold text-sidebar-foreground ring-1 ring-inset ring-border'
                          )}
                        >
                          <item.icon className={cn('h-4 w-4 opacity-85', item.iconClass)} />
                          <span>{item.name}</span>
                        </Button>
                      </Link>
                    )
                  })}
                </div>
                {section.items.some((item) => item.href === '/notebooks') && (
                  <div className="mt-3">
                    <Suspense fallback={null}>
                      <SidebarSections />
                    </Suspense>
                  </div>
                )}
              </div>
            ))}
          </nav>

          <div className="shrink-0 space-y-2 border-t border-sidebar-border p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
            <div className="grid grid-cols-2 gap-2">
              <ThemeToggle />
              <LanguageToggle />
            </div>
            <Button
              variant="outline"
              className="w-full justify-start gap-2 sidebar-menu-item"
              onClick={() => {
                close()
                logout()
              }}
            >
              <LogOut className="h-4 w-4" />
              {t('common.signOut')}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

/**
 * Bottom menu bar for phones and touch tablets (iPad mini included, in both
 * orientations); replaces the sidebar there. Shown and hidden by the
 * `mobile:` variant in globals.css, so there is no layout flash on load.
 */
export function MobileBottomBar() {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [createMenuOpen, setCreateMenuOpen] = useState(false)

  const meetingIcon = <AudioLines className="size-5" />

  return (
    <>
      <nav
        aria-label={t('mobileNav.label')}
        data-testid="mobile-bottom-bar"
        className="mobile-bottom-bar hidden mobile:grid fixed inset-x-0 bottom-0 z-40 glass-dock grid-cols-3 items-center rounded-none border-x-0 border-b-0 px-6 pb-[env(safe-area-inset-bottom)]"
        style={{ height: `calc(${MOBILE_BAR_HEIGHT} + env(safe-area-inset-bottom))` }}
      >
        <div className="flex justify-start">
          <Button
            variant="ghost"
            size="icon"
            className="size-11 text-sidebar-foreground"
            aria-label={t('mobileNav.openMenu')}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(true)}
          >
            <Menu className="size-5" />
          </Button>
        </div>

        <div className="flex justify-center">
          <DropdownMenu open={createMenuOpen} onOpenChange={setCreateMenuOpen}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="default"
                size="icon"
                className="size-12 rounded-full"
                aria-label={t('common.create')}
              >
                <Plus className="size-6" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="center" sideOffset={10} className="w-52">
              <CreateMenuItems onSelected={() => setCreateMenuOpen(false)} />
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="flex justify-end">
          {MEETING_ROUTE ? (
            <Button
              asChild
              variant="ghost"
              size="icon"
              className="size-11 text-teal"
              aria-label={t('mobileNav.startMeeting')}
            >
              <Link href={MEETING_ROUTE}>{meetingIcon}</Link>
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="icon"
              className="size-11 text-sidebar-foreground"
              aria-label={`${t('mobileNav.startMeeting')} (${t('mobileNav.meetingComingSoon')})`}
              title={t('mobileNav.meetingComingSoon')}
              disabled
            >
              {meetingIcon}
            </Button>
          )}
        </div>
      </nav>

      <MobileMenuSheet open={menuOpen} onOpenChange={setMenuOpen} />
    </>
  )
}
