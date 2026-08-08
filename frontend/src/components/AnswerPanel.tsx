// Answer rendering (spec §8.5): arrangement is artifact-driven and
// run-time-frozen. Artifact with presentation 'a2ui_first' → structured view
// primary, raw collapsed behind "view raw response". 'raw_first' (or legacy
// artifacts) → raw primary, artifact collapsed behind "show structured
// summary". No artifact → raw only, no toggle at all (the formatter was off
// or failed at run time — there is nothing to fall back to).
import { useState } from 'react'
import { AnswerUiView } from './AnswerUiView'
import { ChartSvg, type ChartSpec } from './ChartSvg'
import { Markdown } from './Markdown'

export interface AnswerUiPayload {
  a2ui?: unknown[]
  charts?: ChartSpec[]
  presentation?: string
  coverage?: number
}

const RAW_BUBBLE =
  'break-words rounded-lg rounded-bl-sm border border-slate-800 bg-void-900/70 px-3.5 py-2 text-sm leading-relaxed text-slate-200'
const STRUCTURED_SHELL =
  'rounded-lg rounded-bl-sm border border-slate-800 bg-void-900/70 px-3.5 py-2.5 space-y-2'

function CoverageBadge({ coverage, flagBelow }: { coverage?: number; flagBelow?: number }) {
  if (coverage == null) return null
  const low = flagBelow != null && coverage < flagBelow
  return (
    <span
      title="content coverage: numbers/URLs/code spans of the raw answer retained by the structured view"
      className={`ml-2 font-mono text-[9px] uppercase tracking-wider ${
        low ? 'text-amber-400' : 'text-slate-600'
      }`}
    >
      coverage {coverage}%{low ? ' ⚠' : ''}
    </span>
  )
}

function ToolCharts({ charts }: { charts: ChartSpec[] }) {
  if (!charts.length) return null
  return (
    <div className="mt-1.5 space-y-2">
      {charts.map((c, i) => (
        <ChartSvg key={i} spec={c} />
      ))}
    </div>
  )
}

export function AnswerBlock({
  markdown,
  payload,
  toolCharts,
  coverageFlagBelow,
  streaming = false,
}: {
  markdown: string
  payload: AnswerUiPayload | null | undefined
  toolCharts?: unknown[] | null
  coverageFlagBelow?: number
  streaming?: boolean
}) {
  const [showAlt, setShowAlt] = useState(false)
  const charts = (toolCharts ?? []) as ChartSpec[]
  const hasArtifact = !!payload && (!!payload.a2ui || !!payload.charts?.length)
  const a2uiFirst = hasArtifact && payload?.presentation === 'a2ui_first'

  const rawView = (
    <div className={RAW_BUBBLE}>
      <Markdown text={markdown} />
      {streaming && <span className="animate-blink text-accent-400">▮</span>}
    </div>
  )
  const structuredView = hasArtifact ? (
    <div className={STRUCTURED_SHELL}>
      {payload?.charts?.map((c, i) => <ChartSvg key={i} spec={c} />)}
      {payload?.a2ui && <AnswerUiView messages={payload.a2ui} />}
    </div>
  ) : null

  if (!hasArtifact) {
    // formatter off or failed at run time: raw renders directly — no toggle
    return (
      <div>
        {rawView}
        <ToolCharts charts={charts} />
      </div>
    )
  }

  if (a2uiFirst) {
    return (
      <div>
        {structuredView}
        <ToolCharts charts={charts} />
        <div className="mt-1.5">
          <button
            onClick={() => setShowAlt(!showAlt)}
            className="font-mono text-[10px] tracking-wider text-slate-500 uppercase transition-colors hover:text-accent-400"
          >
            {showAlt ? '▾ hide raw response' : '▸ view raw response'}
          </button>
          <CoverageBadge coverage={payload?.coverage} flagBelow={coverageFlagBelow} />
          {showAlt && <div className="animate-rise mt-1.5">{rawView}</div>}
        </div>
      </div>
    )
  }

  return (
    <div>
      {rawView}
      <ToolCharts charts={charts} />
      <div className="mt-1.5">
        <button
          onClick={() => setShowAlt(!showAlt)}
          className="font-mono text-[10px] tracking-wider text-slate-500 uppercase transition-colors hover:text-accent-400"
        >
          {showAlt ? '▾ hide structured summary' : '▸ show structured summary'}
        </button>
        <CoverageBadge coverage={payload?.coverage} flagBelow={coverageFlagBelow} />
        {showAlt && <div className="animate-rise mt-1.5">{structuredView}</div>}
      </div>
    </div>
  )
}

/** Trace view (Runs page): the audit surface — everything expanded. */
export function AnswerTrace({
  markdown,
  payload,
  toolCharts,
}: {
  markdown: string | null
  payload: AnswerUiPayload | null | undefined
  toolCharts?: unknown[] | null
}) {
  const charts = (toolCharts ?? []) as ChartSpec[]
  const hasArtifact = !!payload && (!!payload.a2ui || !!payload.charts?.length)
  return (
    <div className="space-y-2">
      {markdown && (
        <div className={RAW_BUBBLE}>
          <Markdown text={markdown} />
        </div>
      )}
      <ToolCharts charts={charts} />
      {hasArtifact && (
        <div>
          <div className="mb-1 font-mono text-[9px] uppercase tracking-widest text-slate-500">
            structured artifact
            <CoverageBadge coverage={payload?.coverage} />
          </div>
          <div className={STRUCTURED_SHELL}>
            {payload?.charts?.map((c, i) => <ChartSvg key={i} spec={c} />)}
            {payload?.a2ui && <AnswerUiView messages={payload.a2ui} />}
          </div>
        </div>
      )}
    </div>
  )
}
