import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { Button, Drawer, Field, Select, TextInput, Toggle } from '../components/ui'

// M53 accessibility pass: a Field is a real label bound to its control, a
// switch is announced by its field name, icon-only buttons name themselves,
// and the drawer's close control is named.

describe('Field ↔ control association (M53)', () => {
  it('binds the label to a text input', () => {
    render(
      <Field label="Workspace name" hint="shown in the header">
        <TextInput defaultValue="x" />
      </Field>,
    )
    const input = screen.getByLabelText('Workspace name')
    expect(input).toHaveAttribute('aria-describedby')
    expect(input).toHaveAccessibleDescription('shown in the header')
  })

  it('binds the label to a select', () => {
    render(
      <Field label="Mode">
        <Select defaultValue="a">
          <option value="a">a</option>
        </Select>
      </Field>,
    )
    expect(screen.getByRole('combobox', { name: 'Mode' })).toBeInTheDocument()
  })

  it('names a switch after its field', () => {
    render(
      <Field label="Decay sweep">
        <Toggle checked={false} onChange={() => undefined} />
      </Field>,
    )
    expect(screen.getByRole('switch', { name: 'Decay sweep' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('leaves a wrapper child alone and renders `after` outside the association', () => {
    render(
      <Field label="Pair" after={<span>note</span>}>
        <div>
          <TextInput aria-label="first" />
          <TextInput aria-label="second" />
        </div>
      </Field>,
    )
    expect(screen.getByRole('textbox', { name: 'first' })).toBeInTheDocument()
    expect(screen.getByText('note')).toBeInTheDocument()
  })
})

describe('named controls (M53)', () => {
  it('icon-only buttons carry an accessible name and tab semantics when asked', () => {
    render(
      <>
        <Button aria-label="mark accepted">✓</Button>
        <Button role="tab" aria-selected>
          Inbox
        </Button>
      </>,
    )
    expect(screen.getByRole('button', { name: 'mark accepted' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Inbox' })).toHaveAttribute('aria-selected', 'true')
  })

  it('the drawer close control is named', () => {
    const onClose = vi.fn()
    render(
      <Drawer open onClose={onClose} title="t">
        body
      </Drawer>,
    )
    screen.getByRole('button', { name: 'close' }).click()
    expect(onClose).toHaveBeenCalled()
  })
})
