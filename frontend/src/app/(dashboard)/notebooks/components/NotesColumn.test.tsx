import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ExplainerJob, NoteResponse } from '@/lib/types/api'
import { NotesColumn } from './NotesColumn'

interface MockNoteEditorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebookId: string
  note?: NoteResponse
}

vi.mock('./NoteEditorDialog', () => ({
  NoteEditorDialog: ({
    open,
    onOpenChange,
    notebookId,
    note,
  }: MockNoteEditorDialogProps) => (
    <div
      data-testid="note-editor-dialog"
      data-open={String(open)}
      data-notebook-id={notebookId}
      data-note-id={note?.id ?? ''}
    >
      <button onClick={() => onOpenChange(false)}>close editor</button>
    </div>
  ),
}))

const uploadAsync = vi.fn()
vi.mock('@/lib/hooks/use-notes', () => ({
  useDeleteNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUploadNoteFile: () => ({ isPending: false, mutateAsync: uploadAsync }),
}))

const explainerState = { start: vi.fn(), isStarting: false }
const jobsState: { jobs: ExplainerJob[]; dismiss: ReturnType<typeof vi.fn>; isLoading: boolean } = {
  jobs: [],
  dismiss: vi.fn(),
  isLoading: false,
}
vi.mock('@/lib/hooks/use-explainers', () => ({
  useGenerateExplainer: () => explainerState,
  useExplainerJobs: () => jobsState,
}))

const infographicState = { start: vi.fn(), isStarting: false }
const infographicJobsState: { jobs: ExplainerJob[]; dismiss: ReturnType<typeof vi.fn>; isLoading: boolean } = {
  jobs: [],
  dismiss: vi.fn(),
  isLoading: false,
}
vi.mock('@/lib/hooks/use-infographics', () => ({
  useGenerateInfographic: () => infographicState,
  useInfographicJobs: () => infographicJobsState,
}))

const fetchFile = vi.fn()
vi.mock('@/lib/api/notes', () => ({
  notesApi: { fetchFile: (...a: unknown[]) => fetchFile(...a) },
}))

const toast = vi.fn()
vi.mock('@/lib/hooks/use-toast', () => ({
  useToast: () => ({ toast }),
}))

vi.mock('./NoteFileViewer', () => ({
  NoteFileViewer: ({ note, open }: { note: NoteResponse | null; open: boolean }) => (
    <div data-testid="file-viewer" data-open={String(open)} data-note-id={note?.id ?? ''} />
  ),
}))

vi.mock('@/lib/stores/notebook-columns-store', () => ({
  useNotebookColumnsStore: () => ({
    notesCollapsed: false,
    toggleNotes: vi.fn(),
  }),
}))

vi.mock('./NotebookMeetings', () => ({ NotebookMeetings: () => <div data-testid="notebook-meetings" /> }))

vi.mock('./NotebookPodcasts', () => ({
  NotebookPodcasts: () => <div data-testid="notebook-podcasts" />,
}))

const notebookId = 'notebook:123'
const existingNote: NoteResponse = {
  id: 'note:456',
  title: 'Existing note',
  content: 'Existing note content',
  note_type: 'human',
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
}

function renderNotes(notes: NoteResponse[]) {
  render(
    <NotesColumn
      notes={notes}
      isLoading={false}
      notebookId={notebookId}
    />
  )
  return screen.getByTestId('note-editor-dialog')
}

describe('NotesColumn', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('opens, closes, and reopens the editor in create mode with loaded notes', () => {
    const editor = renderNotes([existingNote])

    fireEvent.click(screen.getByText('common.writeNote'))

    expect(editor).toHaveAttribute('data-open', 'true')
    expect(editor).toHaveAttribute('data-notebook-id', notebookId)
    expect(editor).toHaveAttribute('data-note-id', '')

    fireEvent.click(screen.getByText('close editor'))
    expect(editor).toHaveAttribute('data-open', 'false')

    fireEvent.click(screen.getByText('common.writeNote'))
    expect(editor).toHaveAttribute('data-open', 'true')
    expect(editor).toHaveAttribute('data-note-id', '')
  })

  it('opens the editor in create mode when the notes list is empty', () => {
    const editor = renderNotes([])

    fireEvent.click(screen.getByText('common.writeNote'))

    expect(editor).toHaveAttribute('data-open', 'true')
    expect(editor).toHaveAttribute('data-notebook-id', notebookId)
    expect(editor).toHaveAttribute('data-note-id', '')
  })

  it('clears the selected note before opening the editor in create mode', () => {
    const editor = renderNotes([existingNote])

    fireEvent.click(screen.getByText(existingNote.title!))
    expect(editor).toHaveAttribute('data-open', 'true')
    expect(editor).toHaveAttribute('data-note-id', existingNote.id)

    fireEvent.click(screen.getByText('close editor'))
    fireEvent.click(screen.getByText('common.writeNote'))

    expect(editor).toHaveAttribute('data-open', 'true')
    expect(editor).toHaveAttribute('data-note-id', '')
  })

  describe('files', () => {
    const fileNote: NoteResponse = {
      id: 'note:file',
      title: 'report.pdf',
      content: 'extracted text',
      note_type: 'human',
      created: '2026-01-01T00:00:00Z',
      updated: '2026-01-01T00:00:00Z',
      attachment: { name: 'report.pdf', type: 'application/pdf', size: 2048 },
    }
    const file = (name: string) => new File(['x'], name)
    const drop = (card: Element, files: File[], types = ['Files']) =>
      fireEvent.drop(card, { dataTransfer: { types, files } })
    const card = () => screen.getByText('common.notes').closest('[class*="flex-col"]') as Element

    beforeEach(() => uploadAsync.mockResolvedValue({}))

    it('uploads dropped supported files into this notebook, one by one', async () => {
      renderNotes([])
      drop(card(), [file('a.pdf'), file('b.docx')])

      await waitFor(() => expect(uploadAsync).toHaveBeenCalledTimes(2))
      expect(uploadAsync).toHaveBeenNthCalledWith(1, { notebookId, file: expect.objectContaining({ name: 'a.pdf' }) })
      expect(uploadAsync).toHaveBeenNthCalledWith(2, { notebookId, file: expect.objectContaining({ name: 'b.docx' }) })
    })

    it('rejects unsupported files with a message and uploads only the rest', async () => {
      renderNotes([])
      drop(card(), [file('malware.exe'), file('ok.md')])

      await waitFor(() => expect(uploadAsync).toHaveBeenCalledTimes(1))
      expect(uploadAsync).toHaveBeenCalledWith({ notebookId, file: expect.objectContaining({ name: 'ok.md' }) })
      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'noteFiles.unsupportedTitle' }))
    })

    it('ignores drags that are not files', () => {
      renderNotes([])
      drop(card(), [], ['text/plain'])
      expect(uploadAsync).not.toHaveBeenCalled()
    })

    it('shows a drop overlay while files are dragged over and hides it on drop', () => {
      renderNotes([])
      fireEvent.dragOver(card(), { dataTransfer: { types: ['Files'] } })
      expect(screen.getByTestId('notes-drop-overlay')).toBeInTheDocument()

      drop(card(), [])
      expect(screen.queryByTestId('notes-drop-overlay')).toBeNull()
    })

    it('uploads files chosen with the Add file button', async () => {
      renderNotes([])
      fireEvent.change(screen.getByTestId('notes-file-input'), { target: { files: [file('c.html')] } })
      await waitFor(() => expect(uploadAsync).toHaveBeenCalledTimes(1))
    })

    it('opens the viewer, not the editor, when a file card is clicked', () => {
      const editor = renderNotes([fileNote])
      fireEvent.click(screen.getByText('report.pdf'))

      expect(screen.getByTestId('file-viewer')).toHaveAttribute('data-open', 'true')
      expect(screen.getByTestId('file-viewer')).toHaveAttribute('data-note-id', 'note:file')
      expect(editor).toHaveAttribute('data-open', 'false')
    })

    it('still opens the editor for ordinary notes', () => {
      const editor = renderNotes([existingNote])
      fireEvent.click(screen.getByText('Existing note'))

      expect(editor).toHaveAttribute('data-open', 'true')
      expect(screen.getByTestId('file-viewer')).toHaveAttribute('data-open', 'false')
    })
  })

  it('opens the Generate Explainer dialog and shows explainer jobs from the server', () => {
    jobsState.jobs = [
      { job_id: 'command:a', status: 'running', requested_at: new Date().toISOString(), note_id: null, title: null, error_message: null },
      { job_id: 'command:b', status: 'failed', requested_at: new Date().toISOString(), note_id: null, title: null, error_message: 'No model configured' },
    ]
    renderNotes([])
    expect(screen.getByTestId('explainer-pending')).toBeInTheDocument()
    expect(screen.getByTestId('explainer-job-failed')).toHaveTextContent('No model configured')
    fireEvent.click(screen.getByRole('button', { name: 'explainer.dismiss' }))
    expect(jobsState.dismiss).toHaveBeenCalledWith('command:b')
    fireEvent.click(screen.getByRole('button', { name: 'explainer.generate' }))
    expect(screen.getByTestId('explainer-option-sources')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('explainer-option-repo')).toBeDisabled()
    jobsState.jobs = []
  })

  it('marks generated explainers and opens them in the viewer', () => {
    renderNotes([
      {
        ...existingNote,
        id: 'note:exp',
        title: 'Tides explained',
        note_type: 'ai',
        explainer: true,
        attachment: { name: 'Tides-explained.html', type: 'text/html', size: 2048 },
      },
    ])
    expect(screen.getByText('explainer.badge')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Tides explained'))
    expect(screen.getByTestId('file-viewer')).toHaveAttribute('data-note-id', 'note:exp')
  })

  it('shows explainer jobs first, then notes, as square cards in one grid', () => {
    jobsState.jobs = [
      { job_id: 'command:a', status: 'running', requested_at: new Date().toISOString(), note_id: null, title: null, error_message: null },
    ]
    renderNotes([existingNote, { ...existingNote, id: 'note:2', title: 'Second note' }])
    const grid = screen.getByTestId('notes-grid')
    const cards = Array.from(grid.children)
    expect(cards).toHaveLength(3)
    expect(cards[0]).toHaveAttribute('data-testid', 'explainer-pending')
    expect(cards[1]).toHaveTextContent('Existing note')
    expect(cards[2]).toHaveTextContent('Second note')
    for (const card of cards) expect(card.className).toContain('aspect-square')
    expect(screen.queryByText('notebooks.noNotesYet')).toBeNull()
    jobsState.jobs = []
  })

  it('shows the empty state only when there are no notes and no explainer jobs', () => {
    renderNotes([])
    expect(screen.getByText('notebooks.noNotesYet')).toBeInTheDocument()
    expect(screen.queryByTestId('notes-grid')).toBeNull()
  })

  it('opens the Generate Infographic dialog from its button', () => {
    renderNotes([existingNote])
    fireEvent.click(screen.getByRole('button', { name: 'infographic.generate' }))
    expect(screen.getByText('infographic.dialogDesc')).toBeInTheDocument()
  })

  it('marks infographics, shows the image as a thumbnail and opens the viewer', async () => {
    fetchFile.mockResolvedValue(new Blob(['<svg xmlns="http://www.w3.org/2000/svg"/>']))
    const createObjectURL = vi.fn(() => 'blob:thumb')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    renderNotes([
      {
        ...existingNote,
        id: 'note:info',
        title: 'Tides at a glance',
        note_type: 'ai',
        infographic: true,
        attachment: { name: 'Tides.svg', type: 'image/svg+xml', size: 4096 },
      },
    ])
    expect(screen.getByText('infographic.badge')).toBeInTheDocument()
    expect(await screen.findByTestId('infographic-thumbnail')).toHaveAttribute('src', 'blob:thumb')
    expect(fetchFile).toHaveBeenCalledWith('note:info')
    fireEvent.click(screen.getByText('Tides at a glance'))
    expect(screen.getByTestId('file-viewer')).toHaveAttribute('data-note-id', 'note:info')
  })

  it('shows infographic jobs with their own wording', () => {
    infographicJobsState.jobs = [
      { job_id: 'command:i', status: 'running', requested_at: new Date().toISOString(), note_id: null, title: null, error_message: null },
    ]
    renderNotes([])
    expect(screen.getByText('infographic.generatingOne')).toBeInTheDocument()
    expect(screen.queryByText('notebooks.noNotesYet')).toBeNull()
    infographicJobsState.jobs = []
  })
})
