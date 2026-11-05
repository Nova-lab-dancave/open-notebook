import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { CreateMenuItems } from './CreateMenuItems'
import { MobileBottomBar } from './MobileBottomBar'

vi.mock('@/lib/hooks/use-sections', () => ({
  useSections: () => ({ data: [{ id: 'section:1', name: 'Personal', folder_count: 1 }] }),
}))

describe('MobileBottomBar', () => {
  it('renders the menu, create and meeting buttons', () => {
    render(<MobileBottomBar />)

    const bar = screen.getByTestId('mobile-bottom-bar')
    // Hidden by default; the `mobile:` variant shows it on small or touch screens.
    expect(bar.className.split(/\s+/)).toContain('hidden')
    expect(bar.className.split(/\s+/)).toContain('mobile:grid')

    expect(screen.getByRole('button', { name: 'mobileNav.openMenu' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'common.create' })).toBeDefined()
  })

  it('keeps the meeting button disabled until meetings land', () => {
    render(<MobileBottomBar />)

    const meeting = screen.getByRole('button', { name: /mobileNav\.startMeeting/ })
    expect(meeting).toBeDisabled()
    expect(meeting.getAttribute('title')).toBe('mobileNav.meetingComingSoon')
  })

  it('opens the sidebar navigation as a sheet and closes it on navigation', () => {
    render(<MobileBottomBar />)

    expect(screen.queryByTestId('mobile-menu-sheet')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'mobileNav.openMenu' }))

    const sheet = screen.getByTestId('mobile-menu-sheet')
    expect(sheet.querySelector('a[href="/notebooks"]')).not.toBeNull()
    expect(sheet.querySelector('a[href="/settings/models"]')).not.toBeNull()
    expect(screen.getByText('Personal')).toBeDefined()
    expect(screen.getByText('common.signOut')).toBeDefined()

    // jsdom can't navigate; stop the link's default so only our close runs.
    const link = sheet.querySelector('a[href="/sources"]') as HTMLElement
    link.addEventListener('click', (event) => event.preventDefault())
    fireEvent.click(link)
    expect(screen.queryByTestId('mobile-menu-sheet')).toBeNull()
  })
})

describe('CreateMenuItems', () => {
  it('opens the matching create dialog and reports the selection', () => {
    const openSourceDialog = vi.fn()
    const openNotebookDialog = vi.fn()
    const openPodcastDialog = vi.fn()
    vi.mocked(useCreateDialogs).mockReturnValue({
      openSourceDialog,
      openNotebookDialog,
      openPodcastDialog,
    } as unknown as ReturnType<typeof useCreateDialogs>)
    const onSelected = vi.fn()

    render(
      <DropdownMenu open>
        <DropdownMenuTrigger>open</DropdownMenuTrigger>
        <DropdownMenuContent>
          <CreateMenuItems onSelected={onSelected} />
        </DropdownMenuContent>
      </DropdownMenu>
    )

    fireEvent.click(screen.getByText('common.notebook'))

    expect(onSelected).toHaveBeenCalledTimes(1)
    expect(openNotebookDialog).toHaveBeenCalledTimes(1)
    expect(openSourceDialog).not.toHaveBeenCalled()
    expect(openPodcastDialog).not.toHaveBeenCalled()
  })
})
