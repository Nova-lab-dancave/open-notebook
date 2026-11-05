'use client'

import { AppSidebar } from './AppSidebar'
import { MobileBottomBar } from './MobileBottomBar'
import { SetupBanner } from './SetupBanner'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex h-[calc(100dvh-var(--player-offset,0px))] overflow-hidden">
      <AppSidebar />
      {/* On mobile the fixed bottom bar covers the foot of the screen, so main stops above it. */}
      <main className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden mobile:pb-[calc(var(--mobile-bar-height)+env(safe-area-inset-bottom))]">
        <SetupBanner />
        {children}
      </main>
      <MobileBottomBar />
    </div>
  )
}
