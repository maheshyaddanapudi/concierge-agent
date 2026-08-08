// Native themed table (spec §8.5): real table chrome for `table` components
// in the structured document — header row, zebra striping, numeric columns
// right-aligned in monospace, horizontal scroll for wide tables.
export interface TableSpec {
  columns: string[]
  rows: string[][]
}

const NUMERIC = /^[\s$€£]?-?\d[\d,]*(\.\d+)?\s?(%|ms|s|units?|x)?$/i

export function TableBlock({ spec }: { spec: TableSpec }) {
  if (!spec.rows.length) return null
  const cols = spec.columns.length
    ? spec.columns
    : Array.from({ length: spec.rows[0]?.length ?? 0 }, () => '')
  const numeric = cols.map((_, ci) =>
    spec.rows.every((r) => r[ci] == null || r[ci] === '' || NUMERIC.test(String(r[ci]).trim())),
  )
  return (
    <div className="overflow-x-auto rounded-md border border-slate-800 bg-void-900/50">
      <table className="w-full border-collapse text-sm">
        {spec.columns.length > 0 && (
          <thead>
            <tr className="border-b border-slate-700/80">
              {cols.map((c, i) => (
                <th
                  key={i}
                  className={`px-3 py-1.5 font-mono text-[10px] font-semibold tracking-wider text-slate-400 uppercase ${
                    numeric[i] ? 'text-right' : 'text-left'
                  }`}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {spec.rows.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 1 ? 'bg-slate-800/20' : ''}>
              {cols.map((_, ci) => (
                <td
                  key={ci}
                  className={`px-3 py-1.5 text-slate-200 ${
                    numeric[ci] ? 'text-right font-mono text-[13px] tabular-nums' : 'text-left'
                  }`}
                >
                  {row[ci] ?? ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
