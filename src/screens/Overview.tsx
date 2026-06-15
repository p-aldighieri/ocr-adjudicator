import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../store'
import { computeStatus, overallProgress } from '../queue'
import type { Item, ItemStatus } from '../types'

const CELL: Record<ItemStatus, string> = {
  untouched: 'bg-slate-800 text-slate-500',
  in_progress: 'bg-amber-500/30 text-amber-200',
  done: 'bg-emerald-500/40 text-emerald-100',
  wrong_page: 'bg-rose-600/40 text-rose-100',
}

export function Overview() {
  const nav = useNavigate()
  const { items, results, dataset } = useStore()
  const [q, setQ] = useState('')

  const years = useMemo(
    () => (dataset?.meta.years ?? [...new Set(items.map((i) => i.year))]).slice().sort((a, b) => a - b),
    [dataset, items],
  )

  const groups = useMemo(() => {
    const m = new Map<string, { title: string; byYear: Record<number, Item> }>()
    for (const it of items) {
      if (!m.has(it.groupKey)) m.set(it.groupKey, { title: it.title, byYear: {} })
      m.get(it.groupKey)!.byYear[it.year] = it
    }
    let arr = [...m.values()].sort((a, b) => a.title.localeCompare(b.title))
    if (q.trim()) arr = arr.filter((g) => g.title.toLowerCase().includes(q.toLowerCase()))
    return arr
  }, [items, q])

  const prog = overallProgress(items, results)

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-slate-800 bg-slate-900/80 px-3 py-2">
        <div className="flex items-center gap-2">
          <h1 className="flex-1 text-base font-semibold text-white">Overview</h1>
          <button onClick={() => nav('/settings')} className="rounded px-2 py-1 text-slate-300 active:bg-slate-800">⚙</button>
          <button onClick={() => nav('/item/_first')} className="rounded bg-sky-600 px-3 py-1 text-sm font-medium text-white">Adjudicate →</button>
        </div>
        <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-400">
          <span className="text-emerald-300">done {prog.done}</span>
          <span className="text-amber-300">partial {prog.inProgress}</span>
          <span className="text-rose-300">wrong {prog.wrongPage}</span>
          <span className="text-slate-500">left {prog.untouched}</span>
          <span className="ml-auto font-mono">{prog.done + prog.wrongPage}/{prog.total}</span>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="filter institutions…"
          className="mt-2 w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-sm text-white outline-none placeholder:text-slate-600"
        />
      </header>

      <div className="flex-1 overflow-auto">
        <table className="border-separate border-spacing-1 text-xs">
          <thead className="sticky top-0 z-10 bg-slate-950">
            <tr>
              <th className="sticky left-0 z-20 bg-slate-950 px-2 py-1 text-left text-slate-400">Institution</th>
              {years.map((y) => (
                <th key={y} className="px-1 py-1 text-slate-400">{String(y).slice(2)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.title}>
                <td className="sticky left-0 z-10 max-w-[44vw] truncate bg-slate-950 px-2 py-1 text-slate-200">{g.title}</td>
                {years.map((y) => {
                  const it = g.byYear[y]
                  if (!it) return <td key={y} className="h-7 w-9 rounded bg-slate-900/40" />
                  const st = computeStatus(it, results[it.id])
                  return (
                    <td key={y} className="p-0">
                      <button
                        onClick={() => nav(`/item/${it.id}`)}
                        title={`${g.title} ${y} — ${st}`}
                        className={`h-7 w-9 rounded text-[10px] ${CELL[st]} ${it.priority >= 0.5 ? 'ring-1 ring-rose-400/60' : ''}`}
                      >
                        {st === 'done' ? '✓' : st === 'wrong_page' ? '⚠' : st === 'in_progress' ? '·' : ''}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-3 py-3 text-[11px] text-slate-600">
          Red ring = high priority (conflict / low confidence). Tap any cell to open it.
        </div>
      </div>
    </div>
  )
}
