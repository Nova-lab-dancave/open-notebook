import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { INFOGRAPHIC_STYLES } from '@/lib/infographic-options'
import { GenerateInfographicDialog } from './GenerateInfographicDialog'

function renderDialog(props: Partial<React.ComponentProps<typeof GenerateInfographicDialog>> = {}) {
  const onGenerate = props.onGenerate ?? vi.fn().mockResolvedValue({ job_id: 'command:1' })
  const onOpenChange = props.onOpenChange ?? vi.fn()
  render(<GenerateInfographicDialog open onOpenChange={onOpenChange} onGenerate={onGenerate} {...props} />)
  return { onGenerate, onOpenChange }
}

describe('GenerateInfographicDialog', () => {
  it('offers every style, with the default selected', () => {
    renderDialog()
    for (const style of INFOGRAPHIC_STYLES) {
      expect(screen.getByTestId(`infographic-style-${style.id}`)).toBeInTheDocument()
    }
    expect(screen.getByTestId('infographic-style-clean-editorial')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('infographic-aspect-portrait')).toHaveAttribute('aria-checked', 'true')
  })

  it('submits the chosen style, shape and trimmed focus, then closes', async () => {
    const { onGenerate, onOpenChange } = renderDialog()
    fireEvent.click(screen.getByTestId('infographic-style-chalkboard'))
    fireEvent.click(screen.getByTestId('infographic-aspect-landscape'))
    fireEvent.change(screen.getByLabelText('infographic.focusLabel'), { target: { value: '  key numbers  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'explainer.submit' }))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(onGenerate).toHaveBeenCalledWith({
      style: 'chalkboard',
      layout: 'auto',
      aspect: 'landscape',
      instructions: 'key numbers',
    })
  })

  it('omits an empty focus', async () => {
    const { onGenerate } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'explainer.submit' }))
    await waitFor(() =>
      expect(onGenerate).toHaveBeenCalledWith({ style: 'clean-editorial', layout: 'auto', aspect: 'portrait' })
    )
  })

  it('cannot start without sources and says why', () => {
    renderDialog({ hasSources: false })
    expect(screen.getByRole('alert')).toHaveTextContent('explainer.noSources')
    expect(screen.getByRole('button', { name: 'explainer.submit' })).toBeDisabled()
  })

  it('stays open when starting fails', async () => {
    const onGenerate = vi.fn().mockRejectedValue(new Error('nope'))
    const { onOpenChange } = renderDialog({ onGenerate })
    fireEvent.click(screen.getByRole('button', { name: 'explainer.submit' }))
    await waitFor(() => expect(onGenerate).toHaveBeenCalled())
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })
})
