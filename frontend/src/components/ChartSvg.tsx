// Themed pure-SVG charts (spec §7.1 chart component): data only, no markup
// surface, colors from the theme's accent ramp so all four themes follow.
export interface ChartSpec {
  kind: 'bar' | 'line' | 'pie'
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

function XLabels({ labels }: { labels: string[] }) {
  const y0 = H - PAD.bottom
  const span = W - PAD.left - PAD.right
  return (
    <g>
      {labels.map((l, i) => (
        <text
          key={i}
          x={PAD.left + span * ((i + 0.5) / labels.length)}
          y={y0 + 13}
          textAnchor="middle"
          fontSize="9"
          fill="var(--color-slate-400)"
        >
          {l.length > 12 ? l.slice(0, 11) + '…' : l}
        </text>
      ))}
    </g>
  )
}

function BarChart({ spec }: { spec: ChartSpec }) {
  const max = niceMax(Math.max(...spec.series.flatMap((s) => s.values)))
  const y0 = H - PAD.bottom
  const span = W - PAD.left - PAD.right
  const slot = span / spec.labels.length
  const barW = Math.min(34, (slot * 0.7) / spec.series.length)
  return (
    <>
      <Axes max={max} />
      <XLabels labels={spec.labels} />
      {spec.series.map((s, si) =>
        s.values.map((v, i) => {
          const h = ((y0 - PAD.top) * v) / max
          const x =
            PAD.left + slot * i + slot / 2 - (barW * spec.series.length) / 2 + si * barW
          return (
            <rect
              key={`${si}-${i}`}
              x={x}
              y={y0 - h}
              width={barW - 2}
              height={h}
              rx={2}
              fill={SERIES_VARS[si % SERIES_VARS.length]}
              opacity={0.9}
            />
          )
        }),
      )}
    </>
  )
}

function LineChart({ spec }: { spec: ChartSpec }) {
  const max = niceMax(Math.max(...spec.series.flatMap((s) => s.values)))
  const y0 = H - PAD.bottom
  const span = W - PAD.left - PAD.right
  const pt = (i: number, v: number) =>
    `${PAD.left + span * ((i + 0.5) / spec.labels.length)},${y0 - ((y0 - PAD.top) * v) / max}`
  return (
    <>
      <Axes max={max} />
      <XLabels labels={spec.labels} />
      {spec.series.map((s, si) => (
        <g key={si}>
          <polyline
            points={s.values.map((v, i) => pt(i, v)).join(' ')}
            fill="none"
            stroke={SERIES_VARS[si % SERIES_VARS.length]}
            strokeWidth={2}
          />
          {s.values.map((v, i) => {
            const [cx, cy] = pt(i, v).split(',')
            return (
              <circle
                key={i}
                cx={cx}
                cy={cy}
                r={3}
                fill={SERIES_VARS[si % SERIES_VARS.length]}
              />
            )
          })}
        </g>
      ))}
    </>
  )
}

function PieChart({ spec }: { spec: ChartSpec }) {
  const values = spec.series[0]?.values ?? []
  const total = values.reduce((a, b) => a + b, 0) || 1
  const cx = W / 2 - 80
  const cy = H / 2
  const r = 70
  let angle = -Math.PI / 2
  const slices = values.map((v, i) => {
    const sweep = (v / total) * Math.PI * 2
    const x1 = cx + r * Math.cos(angle)
    const y1 = cy + r * Math.sin(angle)
    angle += sweep
    const x2 = cx + r * Math.cos(angle)
    const y2 = cy + r * Math.sin(angle)
    const large = sweep > Math.PI ? 1 : 0
    return (
      <path
        key={i}
        d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`}
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
        {spec.kind === 'line' && <LineChart spec={spec} />}
        {spec.kind === 'pie' && <PieChart spec={spec} />}
      </svg>
      {spec.kind !== 'pie' && spec.series.some((s) => s.name) && (
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
