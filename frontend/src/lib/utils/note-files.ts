import { notesApi } from '@/lib/api/notes'

/** Files that can be dropped on the notes pane (mirrors the backend allow-list). */
export const NOTE_FILE_EXTENSIONS = ['.pdf', '.html', '.htm', '.docx', '.txt', '.md', '.markdown']

export type NoteFileKind = 'pdf' | 'html' | 'svg' | 'text'

export function isSupportedNoteFile(file: { name: string }): boolean {
  const name = file.name.toLowerCase()
  return NOTE_FILE_EXTENSIONS.some((ext) => name.endsWith(ext))
}

/** How the viewer shows a file: PDF, HTML and SVG as the original, everything else as extracted text. */
export function noteFileKind(mime: string): NoteFileKind {
  if (mime === 'application/pdf') return 'pdf'
  if (mime === 'text/html') return 'html'
  if (mime === 'image/svg+xml') return 'svg'
  return 'text'
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** True while the user is dragging files (not text or an in-app item) over the page. */
export function isDraggingFiles(event: { dataTransfer: DataTransfer | null }): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

/** Fetch the original file (with auth) and save it under its own name. */
export async function saveNoteFile(noteId: string, name: string, mime: string): Promise<void> {
  const data = await notesApi.fetchFile(noteId)
  saveBlob(new Blob([data], { type: mime }), name)
}

/** Save a blob under a file name (via a temporary object URL). */
export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/**
 * Render an SVG to a PNG at `scale` times its intrinsic size. Works because a
 * generated infographic is sanitised to have no external references, so the
 * canvas is never tainted.
 */
export async function svgToPng(svg: Blob, scale = 2): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))
  try {
    const image = new Image()
    image.decoding = 'async'
    image.src = url
    await image.decode()
    const width = image.naturalWidth || 1080
    const height = image.naturalHeight || 1920
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(width * scale)
    canvas.height = Math.round(height * scale)
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Canvas is not available')
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((png) => (png ? resolve(png) : reject(new Error('PNG export failed'))), 'image/png')
    )
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** File name with its extension swapped, e.g. `Tides.svg` -> `Tides.png`. */
export function withExtension(name: string, ext: string): string {
  const base = name.replace(/\.[^./]+$/, '')
  return `${base || 'infographic'}${ext}`
}
