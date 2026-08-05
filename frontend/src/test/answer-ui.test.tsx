import { render } from '@testing-library/react'
import { AnswerUiView } from '../components/AnswerUiView'

const VALID_A2UI = [
  {
    version: 'v0.9',
    createSurface: {
      surfaceId: 'answer',
      catalogId: 'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json',
    },
  },
  {
    version: 'v0.9',
    updateComponents: {
      surfaceId: 'answer',
      components: [
        { id: 'c1', component: 'Text', text: 'Revenue was down 12%.' },
        { id: 'root', component: 'Column', children: ['c1'] },
      ],
    },
  },
]

describe('AnswerUiView (spec §8.5: official @a2ui/react renderer)', () => {
  it('renders A2UI v0.9 messages through the official processor', () => {
    const { container } = render(<AnswerUiView messages={VALID_A2UI} />)
    expect(container.textContent).toContain('Revenue was down 12%.')
  })

  it('is failure-safe: garbage payloads render nothing, never throw', () => {
    const { container } = render(<AnswerUiView messages={[{ not: 'a2ui' }]} />)
    expect(container.querySelector('.a2ui-answer')?.textContent ?? '').toBe('')
  })
})
