import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ExplainerJob } from '@/lib/types/api'
import { ExplainerJobRow, QUEUED_WARNING_MS } from './ExplainerJobRow'

const NOW = Date.parse('2026-11-05T16:00:00Z')
const job = (patch: Partial<ExplainerJob>): ExplainerJob => ({
  job_id: 'command:1',
  status: 'queued',
  requested_at: new Date(NOW).toISOString(),
  note_id: null,
  title: null,
  error_message: null,
  ...patch,
})

describe('ExplainerJobRow', () => {
  it('shows a generating row for a fresh job', () => {
    render(<ExplainerJobRow job={job({})} onDismiss={vi.fn()} now={NOW + 1000} />)
    expect(screen.getByRole('status')).toHaveTextContent('explainer.generatingOne')
  })

  it('warns when a job has sat in the queue (worker not running)', () => {
    render(<ExplainerJobRow job={job({})} onDismiss={vi.fn()} now={NOW + QUEUED_WARNING_MS + 1} />)
    expect(screen.getByRole('status')).toHaveTextContent('explainer.waitingForWorker')
  })

  it('does not warn for a long-running job that the worker has picked up', () => {
    render(<ExplainerJobRow job={job({ status: 'running' })} onDismiss={vi.fn()} now={NOW + 10 * QUEUED_WARNING_MS} />)
    expect(screen.getByRole('status')).toHaveTextContent('explainer.generatingOne')
  })

  it('keeps a failure on screen with its reason', () => {
    render(<ExplainerJobRow job={job({ status: 'failed', error_message: 'Model hit its output limit' })} onDismiss={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Model hit its output limit')
  })
})
