import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { Meeting } from '@/lib/api/meetings'
import { NotebookMeetings } from './NotebookMeetings'

const mocks = vi.hoisted(() => ({ data: [] as Meeting[], start: vi.fn(), edit: vi.fn(), approve: vi.fn(), finish: vi.fn() }))
vi.mock('@/lib/hooks/use-meetings', () => ({ useMeetings: () => ({ data: mocks.data, refresh: vi.fn(), action: { isPending: false, mutate: (fn: () => Promise<unknown>) => void fn() } }) }))
vi.mock('@/lib/hooks/use-meeting-recorder', () => ({ useMeetingRecorder: () => ({ state: 'idle', activeId: null, seconds: 0, error: null, start: mocks.start }) }))
vi.mock('@/lib/api/meetings', () => ({ meetingsApi: { edit: mocks.edit, approve: mocks.approve, finish: mocks.finish } }))
const meeting: Meeting = {
  id: 'meeting:1', revision: 0, title: 'Planning', status: 'review', capture_mode: 'microphone',
  transcript: 'Sam will ship Friday.', summary: 'Delivery agreed.',
  actions: [{ text: 'Ship report', owner: 'Sam', due: 'Friday', evidence: 'Sam will ship Friday.', done: false }],
  total_chunks: 2, missing_chunks: [1], summary_status: 'completed', summary_error: '', note_id: '', interrupted: false,
}
beforeEach(() => { vi.clearAllMocks(); mocks.data = []; mocks.edit.mockResolvedValue({}) })

it('starts shared capture only when explicitly selected', () => {
  render(<NotebookMeetings notebookId="notebook:1" />)
  fireEvent.change(screen.getByLabelText('meetings.title'), { target: { value: 'Standup' } })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'meetings.record' }))
  expect(mocks.start).toHaveBeenCalledWith('Standup', true)
  expect(screen.getByText('meetings.sharedHelp')).toBeInTheDocument()
})
it('shows staging and missing-section warning, then approves explicitly', () => {
  mocks.data = [meeting]
  render(<NotebookMeetings notebookId="notebook:1" />)
  expect(screen.getByText('meetings.toReview')).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('meetings.missing')
  expect(mocks.approve).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'meetings.approve' }))
  expect(mocks.approve).toHaveBeenCalledWith('notebook:1', 'meeting:1')
})
it('can save edits to an approved meeting and cannot approve it twice from the UI', async () => {
  mocks.data = [{ ...meeting, status: 'approved', note_id: 'note:1' }]
  render(<NotebookMeetings notebookId="notebook:1" />)
  expect(screen.queryByRole('button', { name: 'meetings.approve' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'common.edit' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'meetings.summary' }), { target: { value: 'Reviewed summary' } })
  fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
  await waitFor(() => expect(mocks.edit).toHaveBeenCalledWith('notebook:1', 'meeting:1', expect.objectContaining({ summary: 'Reviewed summary', transcript: meeting.transcript })))
})
it('recovers interrupted recordings with an explicit incomplete-recording marker', () => {
  mocks.data = [{ ...meeting, status: 'recording' }]
  render(<NotebookMeetings notebookId="notebook:1" />)
  fireEvent.click(screen.getByRole('button', { name: 'meetings.recover' }))
  expect(mocks.finish).toHaveBeenCalledWith('notebook:1', 'meeting:1', 2, true)
})
