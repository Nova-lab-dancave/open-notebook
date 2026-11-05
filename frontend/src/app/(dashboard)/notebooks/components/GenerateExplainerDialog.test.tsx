import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { GenerateExplainerDialog } from './GenerateExplainerDialog'

function renderDialog(props: Partial<React.ComponentProps<typeof GenerateExplainerDialog>> = {}) {
  const onGenerate = props.onGenerate ?? vi.fn().mockResolvedValue({ job_id: 'command:1' })
  const onOpenChange = props.onOpenChange ?? vi.fn()
  render(
    <GenerateExplainerDialog open onOpenChange={onOpenChange} onGenerate={onGenerate} {...props} />
  )
  return { onGenerate, onOpenChange }
}

describe('GenerateExplainerDialog', () => {
  it('offers three options with only "from sources" available', () => {
    renderDialog()
    expect(screen.getByTestId('explainer-option-sources')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('explainer-option-repo')).toBeDisabled()
    expect(screen.getByTestId('explainer-option-discover')).toBeDisabled()
    expect(screen.getAllByText('explainer.comingSoon')).toHaveLength(2)
  })

  it('submits the trimmed focus and closes', async () => {
    const { onGenerate, onOpenChange } = renderDialog()
    fireEvent.change(screen.getByLabelText('explainer.focusLabel'), { target: { value: '  for kids  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'explainer.submit' }))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(onGenerate).toHaveBeenCalledWith({ mode: 'sources', instructions: 'for kids' })
  })

  it('omits an empty focus', async () => {
    const { onGenerate } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'explainer.submit' }))
    await waitFor(() => expect(onGenerate).toHaveBeenCalledWith({ mode: 'sources' }))
  })

  it('stays open when starting fails', async () => {
    const onGenerate = vi.fn().mockRejectedValue(new Error('nope'))
    const { onOpenChange } = renderDialog({ onGenerate })
    fireEvent.click(screen.getByRole('button', { name: 'explainer.submit' }))
    await waitFor(() => expect(onGenerate).toHaveBeenCalled())
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  it('blocks generation when the notebook has no sources', () => {
    renderDialog({ hasSources: false })
    expect(screen.getByRole('alert')).toHaveTextContent('explainer.noSources')
    expect(screen.getByRole('button', { name: 'explainer.submit' })).toBeDisabled()
  })
})
