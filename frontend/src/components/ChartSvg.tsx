// Themed pure-SVG charts (spec §7.1 chart component): data only, no markup
// surface, colors from the theme's accent ramp so all four themes follow.
export interface ChartSpec {
  kind: 'bar' | 'hbar' | 'stacked_bar' | 'line' | 'area' | 'pie' | 'donut' | 'histogram'
  title: string
  labels: string[]
  series: { name: string; values: number[] }[]
}

const W = 460
const H = 200
const PAD = { top: 14, right: 12, bottom: 34, left: 40 }
const SERIES_VARS = [
  'var(--color-accent-400)',
  'var(--color-amber-400)',
  'var(--color-slate-500)',
  'var(--color-accent-600)',
]

function niceMax(v: number): number {
  if (v <= 0) return 1
  const mag = 10 ** Math.floor(Math.log10(v))
  const n = v / mag
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag
}

function Axes({ max }: { max: number }) {
  const y0 = H - PAD.bottom
  const ticks = [0, 0.5, 1]
  return (
    <g className="text-slate-600">
      <line x1={PAD.left} y1={y0} x2={W - PAD.right} y2={y0} stroke="currentColor" />
      <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={y0} stroke="currentColor" />
      {ticks.map((t) => (
        <text
          key={t}
          x={PAD.left - 5}
          y={y0 - t * (y0 - PAD.top) + 3}
          textAnchor="end"
          fontSize="9"
          fill="var(--color-slate-500)"
        >
          {Math.round(max * t * 100) / 100}
        </text>
      ))}
    </g>
  )
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/

/** Dense label sets thin to ~8 ticks; all-ISO-date labels drop the year
 * after the first tick so time series stay legible. */
function displayLabels(labels: string[]): { text: string; index: number }[] {
  const step = Math.max(1, Math.ceil(labels.length / 8))
  const allDates = labels.length > 1 && labels.every((l) => ISO_DATE.test(l))
  const out: { text: string; index: number }[] = []
  for (let i = 0; i < labels.length; i += step) {
    let text = labels[i]
    if (allDates && i > 0) text = text.slice(5, 10)
    else if (text.length > 12) text = text.slice(0, 11) + '…'
    out.push({ text, index: i })
  }
  return out
}

function XLabels({ labels }: { labels: string[] }) {
  const y0 = H - PAD.bottom
  const span = W - PAD.left - PAD.right
  return (
    <g>
      {displayLabels(labels).map(({ text, index }) => (
        <text
          key={index}
          x={PAD.left + span * ((index + 0.5) / labels.length)}
          y={y0 + 13}
          textAnchor="middle"
          fontSize="9"
          fill="var(--color-slate-400)"
        >
          {text}
        </text>
      ))}
    </g>
  )
}

function BarChart({ spec, gapless = false }: { spec: ChartSpec; gapless?: boolean }) {
  const series = gapless ? spec.series.slice(0, 1) : spec.series
  const max = niceMax(Math.max(...series.flatMap((s) => s.values)))
  const y0 = H - PAD.bottom
  const span = W - PAD.left - PAD.right
  const slot = span / spec.labels.length
  const barW = gapless ? slot : Math.min(34, (slot * 0.7) / series.length)
  return (
    <>
      <Axes max={max} />
      <XLabels labels={spec.labels} />
      {series.map((s, si) =>
        s.values.map((v, i) => {
          const h = ((y0 - PAD.top) * v) / max
          const x = gapless
            ? PAD.left + slot * i
            : PAD.left + slot * i + slot / 2 - (barW * series.length) / 2 + si * barW
          return (
            <rect
              key={`${si}-${i}`}
              x={x}
              y={y0 - h}
              width={gapless ? barW - 1 : barW - 2}
              height={h}
              rx={gapless ? 0 : 2}
              fill={SERIES_VARS[si % SERIES_VARS.length]}
              opacity={0.9}
            />
          )
        }),
      )}
    </>
  )
}

function StackedBarChart({ spec }: { spec: ChartSpec }) {
  const totals = spec.labels.map((_, i) =>
    spec.series.reduce((a, s) => a + (s.values[i] ?? 0), 0),
  )
  const max = niceMax(Math.max(...totals))
  const y0 = H - PAD.bottom
  const span = W - PAD.left - PAD.right
  const slot = span / spec.labels.length
  const barW = Math.min(40, slot * 0.6)
  return (
    <>
      <Axes max={max} />
      <XLabels labels={spec.labels} />
      {spec.labels.map((_, i) => {
        let acc = 0
        return spec.series.map((s, si) => {
          const v = s.values[i] ?? 0
          const h = ((y0 - PAD.top) * v) / max
          const y = y0 - ((y0 - PAD.top) * acc) / max - h
          acc += v
          return (
            <rect
              key={`${si}-${i}`}
              x={PAD.left + slot * i + (slot - barW) / 2}
              y={y}
              width={barW}
              height={h}
              fill={SERIES_VARS[si % SERIES_VARS.length]}
              opacity={0.9}
            />
          )
        })
      })}
    </>
  )
}

function HBarChart({ spec }: { spec: ChartSpec }) {
  const values = spec.series[0]?.values ?? []
  const max = niceMax(Math.max(...values))
  const left = 110
  const span = W - left - PAD.right
  const slot = (H - PAD.top - 10) / spec.labels.length
  const barH = Math.min(20, slot * 0.65)
  return (
    <>
      <line
        x1={left}
        y1={PAD.top}
        x2={left}
        y2={H - 10}
        stroke="currentColor"
        className="text-slate-600"
      />
      {spec.labels.map((l, i) => {
        const w = (span * (values[i] ?? 0)) / max
        const y = PAD.top + slot * i + (slot - barH) / 2
        return (
          <g key={i}>
            <text
              x={left - 6}
              y={y + barH / 2 + 3}
              textAnchor="end"
              fontSize="9"
              fill="var(--color-slate-400)"
            >
              {l.length > 16 ? l.slice(0, 15) + '…' : l}
            </text>
            <rect x={left} y={y} width={w} height={barH} rx={2} fill={SERIES_VARS[0]} opacity={0.9} />
            <text x={left + w + 5} y={y + barH / 2 + 3} fontSize="9" fill="var(--color-slate-500)">
              {values[i]}
            </text>
          </g>
        )
      })}
    </>
  )
}

function LineChart({ spec, filled = false }: { spec: ChartSpec; filled?: boolean }) {
  const max = niceMax(Math.max(...spec.series.flatMap((s) => s.values)))
  const y0 = H - PAD.bottom
  const span = W - PAD.left - PAD.right
  const px = (i: number) => PAD.left + span * ((i + 0.5) / spec.labels.length)
  const py = (v: number) => y0 - ((y0 - PAD.top) * v) / max
  const pt = (i: number, v: number) => `${px(i)},${py(v)}`
  const dense = spec.labels.length > 20
  return (
    <>
      <Axes max={max} />
      <XLabels labels={spec.labels} />
      {spec.series.map((s, si) => (
        <g key={si}>
          {filled && s.values.length > 1 && (
            <polygon
              points={[
                `${px(0)},${y0}`,
                ...s.values.map((v, i) => pt(i, v)),
                `${px(s.values.length - 1)},${y0}`,
              ].join(' ')}
              fill={SERIES_VARS[si % SERIES_VARS.length]}
              opacity={0.18}
            />
          )}
          <polyline
            points={s.values.map((v, i) => pt(i, v)).join(' ')}
            fill="none"
            stroke={SERIES_VARS[si % SERIES_VARS.length]}
            strokeWidth={2}
          />
          {!dense &&
            s.values.map((v, i) => (
              <circle
                key={i}
                cx={px(i)}
                cy={py(v)}
                r={3}
                fill={SERIES_VARS[si % SERIES_VARS.length]}
              />
            ))}
        </g>
      ))}
    </>
  )
}

function PieChart({ spec, innerRatio = 0 }: { spec: ChartSpec; innerRatio?: number }) {
  const values = spec.series[0]?.values ?? []
  const total = values.reduce((a, b) => a + b, 0) || 1
  const cx = W / 2 - 80
  const cy = H / 2
  const r = 70
  const ri = r * innerRatio
  let angle = -Math.PI / 2
  const slices = values.map((v, i) => {
    const sweep = (v / total) * Math.PI * 2
    const a1 = angle
    angle += sweep
    const a2 = angle
    const large = sweep > Math.PI ? 1 : 0
    const x1 = cx + r * Math.cos(a1)
    const y1 = cy + r * Math.sin(a1)
    const x2 = cx + r * Math.cos(a2)
    const y2 = cy + r * Math.sin(a2)
    const d =
      ri > 0
        ? `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} ` +
          `L ${cx + ri * Math.cos(a2)} ${cy + ri * Math.sin(a2)} ` +
          `A ${ri} ${ri} 0 ${large} 0 ${cx + ri * Math.cos(a1)} ${cy + ri * Math.sin(a1)} Z`
        : `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`
    return (
      <path
        key={i}
        d={d}
        fill={SERIES_VARS[i % SERIES_VARS.length]}
        opacity={0.75 + 0.25 * ((i % 3) / 2)}
        stroke="var(--color-void-950)"
        strokeWidth={1}
      />
    )
  })
  return (
    <>
      {slices}
      <g>
        {spec.labels.map((l, i) => (
          <g key={i} transform={`translate(${W / 2 + 30}, ${PAD.top + 8 + i * 16})`}>
            <rect width={9} height={9} rx={2} fill={SERIES_VARS[i % SERIES_VARS.length]} />
            <text x={14} y={8} fontSize="10" fill="var(--color-slate-300)">
              {l} — {Math.round(((values[i] ?? 0) / total) * 100)}%
            </text>
          </g>
        ))}
      </g>
    </>
  )
}

const ROUND_KINDS = new Set(['pie', 'donut'])

export function ChartSvg({ spec }: { spec: ChartSpec }) {
  if (!spec.labels.length || !spec.series.length) return null
  return (
    <div className="rounded-md border border-slate-800 bg-void-900/50 p-2.5">
      {spec.title && (
        <div className="mb-1 px-1 font-mono text-[10px] tracking-wider text-slate-400 uppercase">
          {spec.title}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={spec.title}>
        {spec.kind === 'bar' && <BarChart spec={spec} />}
        {spec.kind === 'histogram' && <BarChart spec={spec} gapless />}
        {spec.kind === 'stacked_bar' && <StackedBarChart spec={spec} />}
        {spec.kind === 'hbar' && <HBarChart spec={spec} />}
        {spec.kind === 'line' && <LineChart spec={spec} />}
        {spec.kind === 'area' && <LineChart spec={spec} filled />}
        {spec.kind === 'pie' && <PieChart spec={spec} />}
        {spec.kind === 'donut' && <PieChart spec={spec} innerRatio={0.55} />}
      </svg>
      {!ROUND_KINDS.has(spec.kind) && spec.series.some((s) => s.name) && (
        <div className="mt-1 flex flex-wrap gap-3 px-1">
          {spec.series.map((s, i) => (
            <span key={i} className="flex items-center gap-1.5 text-[10px] text-slate-400">
              <span
                className="inline-block size-2 rounded-sm"
                style={{ background: SERIES_VARS[i % SERIES_VARS.length] }}
              />
              {s.name || `series ${i + 1}`}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
