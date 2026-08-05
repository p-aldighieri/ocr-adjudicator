import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useStore } from '../store'
import { EvidencePane } from '../components/EvidencePane'
import { ClaimRow, sourceLabel } from '../components/ClaimRow'
import {
  EVENT_SECTION, EVENT_SECTION_TITLE, adjudicableFields, buildQueue, computeStatus,
  decidedCount, itemFields, itemSources, nextUnresolvedIndex, resultKey, type FlatField,
} from '../queue'
import { GROUP_LABEL } from '../types'
import type { ClaimField, ItemStatus } from '../types'

export function Adjudicate() {
  const { id } = useParams()
  const nav = useNavigate()
  const {
    items, results, sources, sourceLabels, settings, setSettings,
    setFieldResult, setInsufficient, setNotes,
  } = useStore()

  const queue = useMemo(
    () => buildQueue(items, results, settings.queueMode, settings.filter),
    [items, results, settings.queueMode, settings.filter],
  )
  const item = useMemo(() => items.find((i) => i.id === id) ?? queue[0], [items, queue, id])
  const qIdx = useMemo(() => queue.findIndex((i) => i.id === item?.id), [queue, item])

  const [activeEvidenceId, setActiveEvidenceId] = useState<string | null>(null)
  const [activeFieldKey, setActiveFieldKey] = useState<string | null>(null)
  const [showHelp, setShowHelp] = useState(false)

  // when the bundle changes, focus its first claim + that claim's first piece of evidence
  useEffect(() => {
    if (!item) return
    const first: FlatField | undefined = itemFields(item)[0]
    setActiveFieldKey(first?.key ?? null)
    setActiveEvidenceId(first?.field.evidenceIds[0] ?? item.evidence[0]?.id ?? null)
  }, [item?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!item) {
    return <div className="p-6 text-center text-slate-400">Nothing in the queue. Check Settings → filter.</div>
  }

  const res = results[item.id]
  const { decided, total } = decidedCount(item, res)
  const status = computeStatus(item, res)
  const flat = itemFields(item)
  const relevantIds = flat.find((f) => f.key === activeFieldKey)?.field.evidenceIds ?? []

  // deliberate: bring this claim's evidence into the pane (label tap)
  const focusField = (key: string, f: ClaimField) => {
    setActiveFieldKey(key)
    if (f.evidenceIds[0]) setActiveEvidenceId(f.evidenceIds[0])
  }
  // value tap / typing: only highlight the claim — leave the evidence pane exactly where it is
  const highlightField = (key: string) => setActiveFieldKey(key)

  const goto = (idx: number) => {
    if (idx >= 0 && idx < queue.length) nav(`/item/${queue[idx].id}`)
  }

  const commitDefaultsAndNext = () => {
    for (const ff of adjudicableFields(item)) {
      if (!res?.fields?.[ff.key] && ff.field.default) {
        const v = ff.field.candidates.find((c) => c.source === ff.field.default)?.value ?? null
        setFieldResult(item.id, ff.key, { choice: ff.field.default, value: v })
      }
    }
    if (qIdx + 1 < queue.length) goto(qIdx + 1)
  }

  const acceptAll = (source: string) => {
    for (const ff of adjudicableFields(item)) {
      const c = ff.field.candidates.find((x) => x.source === source)
      if (c) setFieldResult(item.id, ff.key, { choice: source, value: c.value })
    }
  }

  const jumpUnresolved = () => {
    const ni = nextUnresolvedIndex(queue, results, qIdx)
    if (ni >= 0) goto(ni)
  }

  const presentSources = itemSources(item).sort((a, b) => sources.indexOf(a) - sources.indexOf(b))

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <header className="flex items-center gap-2 border-b border-slate-800 bg-slate-900/80 px-3 py-2">
        <button onClick={() => nav('/overview')} className="rounded px-2 py-1 text-slate-300 active:bg-slate-800">▤</button>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-white">{item.title}</div>
          <div className="flex items-center gap-1.5 truncate text-[11px] text-slate-500">
            <span
              className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-amber-300"
              title="Which backlog this bundle came from"
            >
              {GROUP_LABEL[item.group]}
            </span>
            <span className="truncate">
              {item.subtitle} · {item.books.length} book{item.books.length === 1 ? '' : 's'} · {decided}/{total} claims
            </span>
          </div>
        </div>
        <button
          onClick={() => setShowHelp(true)}
          title="Reading conventions"
          className="rounded-full border border-slate-700 px-2 py-0.5 text-sm text-slate-300 active:bg-slate-800"
        >
          ?
        </button>
        <div className="text-right text-[11px] text-slate-400">
          <div className="font-mono text-sm text-slate-200">{qIdx >= 0 ? qIdx + 1 : '–'}/{queue.length}</div>
          <StatusDot status={status} />
        </div>
      </header>

      {/* queue sort + backlog selector */}
      <div className="flex items-center gap-1.5 border-b border-slate-800 bg-slate-900/50 px-3 py-1 text-[11px]">
        <span className="text-slate-500">Queue</span>
        <SortChip active={settings.queueMode === 'group'} onClick={() => setSettings({ queueMode: 'group' })}>By backlog</SortChip>
        <SortChip active={settings.queueMode === 'state'} onClick={() => setSettings({ queueMode: 'state' })}>By state</SortChip>
        <SortChip active={settings.queueMode === 'priority'} onClick={() => setSettings({ queueMode: 'priority' })}>Priority</SortChip>
        <span className="ml-auto text-slate-600">|</span>
        <SortChip active={settings.filter === 'all'} onClick={() => setSettings({ filter: 'all' })}>All</SortChip>
        <SortChip active={settings.filter === 'unresolved'} onClick={() => setSettings({ filter: 'unresolved' })}>Backlog</SortChip>
      </div>

      {/* reviewer instruction banner */}
      {item.alert && (
        <div className="border-b border-amber-700/40 bg-amber-500/10 px-3 py-2 text-[12px] leading-snug text-amber-200">
          <span className="mr-1">⚠️</span>
          <span className="whitespace-pre-wrap">{item.alert}</span>
        </div>
      )}

      {/* main: stacked on phone, two-pane (evidence | claims) on desktop */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">

      {/* evidence — fixed-height strip on phone, full-height left pane on desktop */}
      <div className="h-[44vh] shrink-0 border-b border-slate-800 lg:h-auto lg:min-h-0 lg:flex-1 lg:border-b-0 lg:border-r">
        <EvidencePane
          evidence={item.evidence}
          activeId={activeEvidenceId}
          onPick={setActiveEvidenceId}
          relevantIds={relevantIds}
          wrapText={settings.wrapText}
        />
      </div>

      {/* right column: claims + nav (full-height side panel on desktop) */}
      <div className="flex min-h-0 flex-1 flex-col lg:w-[520px] lg:flex-none">

      <div className={`flex-1 overflow-y-auto px-3 py-2 ${status === 'insufficient' ? 'opacity-40' : ''}`}>
        {item.note && (
          <p className="mb-2 rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-[12px] leading-snug text-slate-400">
            {item.note}
          </p>
        )}

        <div className="mb-2 flex flex-wrap gap-2">
          {presentSources.map((s) => (
            <QuickBtn key={s} onClick={() => acceptAll(s)}>✓ All {sourceLabel(s, sourceLabels)}</QuickBtn>
          ))}
          <QuickBtn
            onClick={() => setInsufficient(item.id, status !== 'insufficient')}
            active={status === 'insufficient'}
          >
            ⚑ Evidence insufficient
          </QuickBtn>
        </div>

        {item.eventFields && item.eventFields.length > 0 && (
          <ClaimSection title={EVENT_SECTION_TITLE} kind="event">
            {item.eventFields.map((f) => {
              const key = resultKey(EVENT_SECTION, f.key)
              return (
                <ClaimRow
                  key={key}
                  field={f}
                  sources={sources}
                  sourceLabels={sourceLabels}
                  result={res?.fields?.[key]}
                  suggested={!res?.fields?.[key]}
                  onChange={(fr) => setFieldResult(item.id, key, fr)}
                  onFocus={() => focusField(key, f)}
                  onPick={() => highlightField(key)}
                />
              )
            })}
          </ClaimSection>
        )}

        {item.books.map((b) => (
          <ClaimSection key={b.key} title={b.title_as_stated} note={b.note} kind="book">
            {b.fields.map((f) => {
              const key = resultKey(b.key, f.key)
              return (
                <ClaimRow
                  key={key}
                  field={f}
                  sources={sources}
                  sourceLabels={sourceLabels}
                  result={res?.fields?.[key]}
                  suggested={!res?.fields?.[key]}
                  onChange={(fr) => setFieldResult(item.id, key, fr)}
                  onFocus={() => focusField(key, f)}
                  onPick={() => highlightField(key)}
                />
              )
            })}
          </ClaimSection>
        ))}

        <NotesBox
          value={res?.notes ?? ''}
          placeholder={item.notesPrompt ?? 'notes (optional)…'}
          onChange={(t) => setNotes(item.id, t)}
        />
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
        <NavBtn onClick={() => goto(qIdx + 1)} disabled={qIdx < 0 || qIdx + 1 >= queue.length}>Next →</NavBtn>
        <NavBtn onClick={jumpUnresolved}>⚑</NavBtn>
      </nav>
      </div>{/* /right column */}
      </div>{/* /main two-pane */}

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}

function ClaimSection({
  title, note, kind, children,
}: {
  title: string
  note?: string
  kind: 'event' | 'book'
  children: ReactNode
}) {
  return (
    <div className="mb-3 rounded-xl border border-slate-800 bg-slate-900/40 p-3">
      <div className="mb-2 flex items-baseline gap-2">
        <h3 className="text-sm font-semibold text-slate-200">
          <span className="mr-1 text-slate-500">{kind === 'book' ? '📖' : '⚖'}</span>
          {title}
        </h3>
      </div>
      {note && <p className="mb-2 text-[11px] leading-snug text-slate-500">{note}</p>}
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function HelpModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 p-4 text-sm text-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-2 flex items-center">
          <h2 className="flex-1 text-base font-semibold text-white">Reading conventions</h2>
          <button onClick={onClose} className="rounded px-2 py-1 text-slate-400 active:bg-slate-800">✕</button>
        </div>
        <ul className="space-y-2.5 text-[13px] leading-snug">
          <li>
            <b className="text-amber-300">One bundle = one adoption event.</b> Every book listed here was
            adopted by the same board action or statute. If the evidence shows two separate actions,
            say so in the notes and flag the bundle.
          </li>
          <li>
            <b className="text-amber-300">Transcribe as printed.</b> Titles and publishers go in exactly as
            the source spells them (“Ginn &amp; Co.”, not “Ginn and Company”) — normalisation happens later,
            downstream, where it can be undone.
          </li>
          <li>
            <b className="text-amber-300">Not stated vs Can’t tell.</b> <b>Not stated</b> = the source is
            legible and simply does not say. <b>Can’t tell</b> = it is there but illegible, cut off, or
            genuinely ambiguous. They mean different things downstream — do not use one for the other.
          </li>
          <li>
            <b className="text-amber-300">Follow the evidence chips.</b> Tapping a claim’s label jumps the
            left pane to the page/snippet that claim came from. A ring on a chip means the focused claim
            cites it too.
          </li>
          <li>
            <b className="text-amber-300">Evidence insufficient.</b> Use it when the shipped evidence cannot
            settle the bundle at all (wrong page, illegible scan, link rot) — and say what is missing in
            the notes so the builder can re-cut it.
          </li>
        </ul>
      </div>
    </div>
  )
}

function StatusDot({ status }: { status: ItemStatus }) {
  const map: Record<ItemStatus, string> = {
    untouched: 'text-slate-500', in_progress: 'text-amber-400', done: 'text-emerald-400', insufficient: 'text-rose-400',
  }
  const label: Record<ItemStatus, string> = {
    untouched: 'new', in_progress: 'partial', done: 'done', insufficient: 'insufficient',
  }
  return <span className={`text-[10px] ${map[status]}`}>● {label[status]}</span>
}

function SortChip({ children, active, onClick }: { children: ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-2.5 py-0.5 ${active ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300 active:bg-slate-700'}`}
    >
      {children}
    </button>
  )
}

function QuickBtn({ children, onClick, active }: { children: ReactNode; onClick: () => void; active?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-2.5 py-1.5 text-xs ${active ? 'bg-rose-600 text-white' : 'bg-slate-800 text-slate-200 active:bg-slate-700'}`}
    >
      {children}
    </button>
  )
}

function NavBtn({ children, onClick, disabled }: { children: ReactNode; onClick: () => void; disabled?: boolean }) {
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

function NotesBox({
  value, placeholder, onChange,
}: {
  value: string
  placeholder: string
  onChange: (t: string) => void
}) {
  return (
    <div className="mt-1">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={2}
        className="w-full rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600"
      />
    </div>
  )
}
