// The structured summary (spec §8.5): a generated view of the canonical
// answer, collapsed behind a quiet link — the markdown text stays primary.
import { useState } from 'react'
import { AnswerUiView } from './AnswerUiView'
import { ChartSvg, type ChartSpec } from './ChartSvg'

export interface AnswerUiPayload {
  a2ui?: unknown[]
  charts?: ChartSpec[]
}

export function AnswerPanel({
  payload,
  defaultOpen = false,
}: {
  payload: AnswerUiPayload | null | undefined
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  if (!payload || (!payload.a2ui && !payload.charts?.length)) return null
  return (
    <div className="mt-1.5">
      <button
        onClick={() => setOpen(!open)}
        className="font-mono text-[10px] tracking-wider text-slate-500 uppercase transition-colors hover:text-accent-400"
      >
        {open ? '▾ hide structured summary' : '▸ show structured summary'}
      </button>
      {open && (
        <div className="animate-rise mt-1.5 space-y-2">
          {payload.charts?.map((c, i) => <ChartSvg key={i} spec={c} />)}
          {payload.a2ui && <AnswerUiView messages={payload.a2ui} />}
        </div>
      )}
    </div>
  )
}
