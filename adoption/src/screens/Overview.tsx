import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../store'
import { computeStatus, overallProgress, progressByGroup } from '../queue'
import type { Item, ItemStatus, QueueGroup } from '../types'
import { GROUP_LABEL, QUEUE_GROUPS } from '../types'

const DOT: Record<ItemStatus, string> = {
  untouched: 'bg-slate-700',
  in_progress: 'bg-amber-400',
  done: 'bg-emerald-400',
  insufficient: 'bg-rose-500',
}

const ROW: Record<ItemStatus, string> = {
  untouched: 'border-slate-800 bg-slate-900/40',
  in_progress: 'border-amber-500/30 bg-amber-500/5',
  done: 'border-emerald-500/30 bg-emerald-500/5',
  insufficient: 'border-rose-500/30 bg-rose-500/5',
}

const GROUP_BLURB: Record<QueueGroup, string> = {
  new_records: 'Events found by the extractor that no reviewer has seen yet.',
  conflicts: 'Sources or models disagree — read the evidence before choosing.',
  state_laws: 'Statute-level adoptions: one law, often many books.',
}

export function Overview() {
  const nav = useNavigate()
  const { items, results, setSettings } = useStore()
  const [q, setQ] = useState('')

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return items
    return items.filter((i) =>
      i.title.toLowerCase().includes(t) ||
      i.subtitle.toLowerCase().includes(t) ||
      i.state.toLowerCase().includes(t) ||
      String(i.year).includes(t))
  }, [items, q])

  const byGroup = useMemo(() => {
    const m = {} as Record<QueueGroup, Item[]>
    for (const g of QUEUE_GROUPS) m[g] = []
    for (const it of filtered) {
      const bucket = m[it.group]
      if (bucket) bucket.push(it) // tolerate a group the UI does not know about
    }
    for (const g of QUEUE_GROUPS) {
      m[g].sort((a, b) => b.priority - a.priority || a.state.localeCompare(b.state) || a.year - b.year)
    }
    return m
  }, [filtered])

  const prog = overallProgress(items, results)
  const gprog = progressByGroup(items, results)

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-slate-800 bg-slate-900/80 px-3 py-2">
        <div className="flex items-center gap-2">
          <h1 className="flex-1 text-base font-semibold text-white">Adoption queues</h1>
          <button onClick={() => nav('/settings')} className="rounded px-2 py-1 text-slate-300 active:bg-slate-800">⚙</button>
          <button
            onClick={() => { setSettings({ filter: 'all' }); nav('/item/_first') }}
            className="rounded bg-slate-700 px-3 py-1 text-sm font-medium text-slate-100"
          >
            Browse all
          </button>
          <button
            onClick={() => { setSettings({ filter: 'unresolved' }); nav('/item/_first') }}
            disabled={prog.inProgress + prog.untouched === 0}
            className="rounded bg-sky-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-40"
          >
            Continue ({prog.inProgress + prog.untouched}) →
          </button>
        </div>
        <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-400">
          <span className="text-emerald-300">done {prog.done}</span>
          <span className="text-amber-300">partial {prog.inProgress}</span>
          <span className="text-rose-300">insufficient {prog.insufficient}</span>
          <span className="text-slate-500">left {prog.untouched}</span>
          <span className="ml-auto font-mono">{prog.done + prog.insufficient}/{prog.total}</span>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="filter by board, county, state, year…"
          className="mt-2 w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-sm text-white outline-none placeholder:text-slate-600"
        />
      </header>

      <div className="flex-1 overflow-auto px-3 py-3">
        {QUEUE_GROUPS.map((g) => (
          <section key={g} className="mb-5">
            <div className="mb-1 flex items-baseline gap-2">
              <h2 className="text-sm font-semibold text-slate-200">{GROUP_LABEL[g]}</h2>
              <span className="font-mono text-[11px] text-slate-500">
                {gprog[g].done + gprog[g].insufficient}/{gprog[g].total}
              </span>
              <span className="ml-auto text-[11px] text-slate-500">
                <span className="text-emerald-300">{gprog[g].done}</span> ·{' '}
                <span className="text-amber-300">{gprog[g].inProgress}</span> ·{' '}
                <span className="text-rose-300">{gprog[g].insufficient}</span> ·{' '}
                <span className="text-slate-500">{gprog[g].untouched}</span>
              </span>
            </div>
            <p className="mb-2 text-[11px] leading-snug text-slate-600">{GROUP_BLURB[g]}</p>

            {byGroup[g].length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-800 px-3 py-4 text-center text-xs text-slate-600">
                nothing here
              </div>
            )}

            <div className="space-y-1.5">
              {byGroup[g].map((it) => {
                const st = computeStatus(it, results[it.id])
                const nBooks = it.books.length
                return (
                  <button
                    key={it.id}
                    onClick={() => nav(`/item/${it.id}`)}
                    className={`flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-left ${ROW[st]} ${
                      it.priority >= 0.7 ? 'ring-1 ring-rose-400/40' : ''
                    }`}
                  >
                    <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT[st]}`} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-slate-100">{it.title}</span>
                      <span className="block truncate text-[11px] text-slate-500">
                        {it.subtitle} · {nBooks} book{nBooks === 1 ? '' : 's'} · {it.evidence.length} evidence
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-slate-500">{it.state} {it.year}</span>
                  </button>
                )
              })}
            </div>
          </section>
        ))}
        <div className="pb-6 text-[11px] text-slate-600">
          Red ring = high priority. Tap a bundle to adjudicate every book adopted in that event.
        </div>
      </div>
    </div>
  )
}
