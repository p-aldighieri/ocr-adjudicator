import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useStore } from '../store'
import { ImageViewer } from '../components/ImageViewer'
import { FieldRow } from '../components/FieldRow'
import {
  adjudicableFields, buildQueue, computeStatus, nextUnresolvedIndex, decidedCount,
} from '../queue'
import type { Field, Item } from '../types'

export function Adjudicate() {
  const { id } = useParams()
  const nav = useNavigate()
  const { items, results, settings, setFieldResult, setWrongPage, setNotes } = useStore()

  const queue = useMemo(
    () => buildQueue(items, results, settings.queueMode, settings.filter),
    [items, results, settings.queueMode, settings.filter],
  )
  const item = useMemo(() => items.find((i) => i.id === id) ?? queue[0], [items, queue, id])
  const qIdx = useMemo(() => queue.findIndex((i) => i.id === item?.id), [queue, item])

  const [activeImageId, setActiveImageId] = useState<string | null>(null)
  const [activeField, setActiveField] = useState<string | null>(null)

  // when item changes, focus income + its image
  useEffect(() => {
    if (!item) return
    const inc = item.sections[0]?.fields[0]
    setActiveField(inc?.key ?? null)
    setActiveImageId(inc?.imageId ?? item.images[0]?.id ?? null)
  }, [item?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!item) {
    return <div className="p-6 text-center text-slate-400">Nothing in the queue. Check Settings → filter.</div>
  }

  const res = results[item.id]
  const { decided, total } = decidedCount(item, res)
  const status = computeStatus(item, res)

  const focusField = (f: Field) => {
    setActiveField(f.key)
    if (f.imageId) setActiveImageId(f.imageId)
  }

  const goto = (idx: number) => {
    if (idx >= 0 && idx < queue.length) nav(`/item/${queue[idx].id}`)
  }

  const commitDefaultsAndNext = () => {
    for (const f of adjudicableFields(item)) {
      if (!res?.fields?.[f.key] && f.default) {
        const v = f.candidates.find((c) => c.source === f.default)?.value ?? null
        setFieldResult(item.id, f.key, { choice: f.default as never, value: v })
      }
    }
    // advance
    if (qIdx + 1 < queue.length) goto(qIdx + 1)
  }

  const acceptAll = (source: 'claude' | 'codex') => {
    for (const f of adjudicableFields(item)) {
      const c = f.candidates.find((x) => x.source === source)
      if (c) setFieldResult(item.id, f.key, { choice: source, value: c.value })
    }
  }

  const jumpUnresolved = () => {
    const ni = nextUnresolvedIndex(queue, results, qIdx)
    if (ni >= 0) goto(ni)
  }

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <header className="flex items-center gap-2 border-b border-slate-800 bg-slate-900/80 px-3 py-2">
        <button onClick={() => nav('/overview')} className="rounded px-2 py-1 text-slate-300 active:bg-slate-800">▤</button>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-white">
            {item.title} <span className="text-slate-400">— {item.year}</span>
          </div>
          <div className="truncate text-[11px] text-slate-500">
            {item.subtitle}{item.n != null ? ` · #${item.n}` : ''} · {decided}/{total} fields
          </div>
        </div>
        <div className="text-right text-[11px] text-slate-400">
          <div className="font-mono text-sm text-slate-200">{qIdx + 1}/{queue.length}</div>
          <StatusDot status={status} />
        </div>
      </header>

      {/* image viewer */}
      <div className="h-[44vh] shrink-0 border-b border-slate-800">
        <ImageViewer
          images={item.images}
          overlays={item.overlays}
          activeImageId={activeImageId}
          onPickImage={setActiveImageId}
          activeField={activeField}
          showOverlays={settings.showOverlays}
          showRow={settings.showRow}
        />
      </div>

      {/* fields */}
      <div className={`flex-1 overflow-y-auto px-3 py-2 ${status === 'wrong_page' ? 'opacity-40' : ''}`}>
        <div className="mb-2 flex flex-wrap gap-2">
          <QuickBtn onClick={() => acceptAll('claude')}>✓ All Claude</QuickBtn>
          <QuickBtn onClick={() => acceptAll('codex')}>✓ All Codex</QuickBtn>
          <QuickBtn
            onClick={() => setWrongPage(item.id, status !== 'wrong_page')}
            active={status === 'wrong_page'}
          >
            ⚠ Wrong page / uni not here
          </QuickBtn>
        </div>

        {item.sections.map((sec) => (
          <div key={sec.key} className="mb-3 rounded-xl border border-slate-800 bg-slate-900/40 p-3">
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-slate-200">{sec.label}</h3>
              {sec.total != null && (
                <span className="text-[11px] text-slate-500">current total: <span className="font-mono">{sec.total}</span></span>
              )}
            </div>
            <div className="space-y-3">
              {sec.fields.map((f) => (
                <FieldRow
                  key={f.key}
                  field={f}
                  result={res?.fields?.[f.key]}
                  suggested={!res?.fields?.[f.key]}
                  onChange={(fr) => setFieldResult(item.id, f.key, fr)}
                  onFocus={() => focusField(f)}
                />
              ))}
            </div>
          </div>
        ))}

        <NotesBox value={res?.notes ?? ''} onChange={(t) => setNotes(item.id, t)} />
        <div className="h-24" />
      </div>

      {/* bottom nav */}
      <nav className="flex items-center gap-2 border-t border-slate-800 bg-slate-900/90 px-3 py-2">
        <NavBtn onClick={() => goto(qIdx - 1)} disabled={qIdx <= 0}>← Prev</NavBtn>
        <button
          onClick={commitDefaultsAndNext}
          className="flex-1 rounded-lg bg-sky-600 py-2.5 text-center font-semibold text-white active:bg-sky-500"
        >
          Confirm &amp; Next →
        </button>
        <NavBtn onClick={jumpUnresolved}>Next ⚑</NavBtn>
      </nav>
    </div>
  )
}

function StatusDot({ status }: { status: ReturnType<typeof computeStatus> }) {
  const map: Record<string, string> = {
    untouched: 'text-slate-500', in_progress: 'text-amber-400', done: 'text-emerald-400', wrong_page: 'text-rose-400',
  }
  const label: Record<string, string> = {
    untouched: 'new', in_progress: 'partial', done: 'done', wrong_page: 'wrong page',
  }
  return <span className={`text-[10px] ${map[status]}`}>● {label[status]}</span>
}

function QuickBtn({ children, onClick, active }: { children: React.ReactNode; onClick: () => void; active?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-2.5 py-1.5 text-xs ${active ? 'bg-rose-600 text-white' : 'bg-slate-800 text-slate-200 active:bg-slate-700'}`}
    >
      {children}
    </button>
  )
}

function NavBtn({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg bg-slate-800 px-3 py-2.5 text-sm text-slate-200 disabled:opacity-30 active:bg-slate-700"
    >
      {children}
    </button>
  )
}

function NotesBox({ value, onChange }: { value: string; onChange: (t: string) => void }) {
  return (
    <div className="mt-1">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="notes (optional)…"
        rows={2}
        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600"
      />
    </div>
  )
}

export type { Item }
