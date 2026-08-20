import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useStore } from '../store'
import { EvidencePane } from '../components/EvidencePane'
import { ClaimRow, sourceLabel } from '../components/ClaimRow'
import { PrintedTitleRow } from '../components/PrintedTitleRow'
import {
  EVENT_SECTION, EVENT_SECTION_TITLE, adjudicableFields, buildQueue, computeStatus,
  decidedCount, groundTruthAlert, isLegacyTitleField, isMetadataField, itemFields, itemSources,
  nextUnresolvedIndex, printedTitleResultKey, resultKey, sectionVerb, type FlatField,
} from '../queue'
import { FOCUS_LABEL, type ResearchFocus } from '../classifications'
import { CHOICE_NOT_TITLE, GROUP_LABEL, VERB_OPTIONS } from '../types'
import type { ClaimField, ItemStatus } from '../types'
import { ItemResearchTags } from '../components/ItemResearchTags'

/** Foci offered on the review screen itself; an Overview-only focus still shows as a fifth chip. */
const REVIEW_FOCI: ResearchFocus[] = ['all', 'newspapers', 'tables', 'printed']

export function Adjudicate() {
  const { id } = useParams()
  const nav = useNavigate()
  const {
    items, results, sources, sourceLabels, settings, setSettings,
    setFieldResult, addTitle, updateAddedTitle, removeAddedTitle,
    setDateOverride, setVerbOverride, setInsufficient, setNotes,
  } = useStore()

  const queue = useMemo(
    () => buildQueue(items, results, settings.queueMode, settings.filter, settings.focus),
    [items, results, settings.queueMode, settings.filter, settings.focus],
  )
  const allQueue = useMemo(
    () => buildQueue(items, results, settings.queueMode, 'all', settings.focus),
    [items, results, settings.queueMode, settings.focus],
  )
  const item = useMemo(() => items.find((i) => i.id === id) ?? queue[0], [items, queue, id])
  const qIdx = useMemo(() => queue.findIndex((i) => i.id === item?.id), [queue, item])
  const allIdx = useMemo(() => allQueue.findIndex((i) => i.id === item?.id), [allQueue, item])

  const [activeEvidenceId, setActiveEvidenceId] = useState<string | null>(null)
  const [activeFieldKey, setActiveFieldKey] = useState<string | null>(null)
  const [showHelp, setShowHelp] = useState(false)

  // when the bundle changes, focus its first claim + that claim's first piece of evidence
  useEffect(() => {
    if (!item) return
    const firstTitle = item.books[0]
    const first: FlatField | undefined = itemFields(item)[0]
    // v5 book sections carry no fields; their evidence link is the region anchor
    const firstTitleEvidence = firstTitle
      ? item.evidence.find((e) =>
          (e.regions ?? []).some((r) => r.fieldKeys?.includes(printedTitleResultKey(firstTitle.key))))?.id
        ?? firstTitle.fields.flatMap((field) => field.evidenceIds).find(Boolean)
      : undefined
    const timer = window.setTimeout(() => {
      setActiveFieldKey(firstTitle ? printedTitleResultKey(firstTitle.key) : (first?.key ?? null))
      setActiveEvidenceId(
        firstTitleEvidence
        ?? first?.field.evidenceIds[0]
        ?? item.evidence[0]?.id
        ?? null,
      )
    }, 0)
    return () => window.clearTimeout(timer)
  }, [item?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!item) {
    return (
      <div className="p-6 text-center text-slate-400">
        Nothing in this queue.
        {settings.focus !== 'all' && (
          <button
            onClick={() => setSettings({ focus: 'all' })}
            className="ml-2 rounded bg-slate-800 px-2 py-1 text-xs text-sky-300 active:bg-slate-700"
          >
            Clear “{FOCUS_LABEL[settings.focus]}” focus
          </button>
        )}
      </div>
    )
  }

  const res = results[item.id]
  const { decided, total } = decidedCount(item, res)
  const status = computeStatus(item, res)
  const hasEventDate = item.eventFields?.some((f) => f.key === 'date') ?? false
  const shownFoci = REVIEW_FOCI.includes(settings.focus) ? REVIEW_FOCI : [...REVIEW_FOCI, settings.focus]

  // v5 book sections carry no ClaimFields, so a title's evidence comes from the
  // region anchors (fieldKeys) the builder attached; claim evidenceIds remain the fallback
  const evidenceForTitle = (sectionKey: string): string[] => {
    const key = printedTitleResultKey(sectionKey)
    const viaRegions = item.evidence
      .filter((e) => (e.regions ?? []).some((r) => r.fieldKeys?.includes(key)))
      .map((e) => e.id)
    if (viaRegions.length > 0) return viaRegions
    return item.books.find((b) => b.key === sectionKey)
      ?.fields.flatMap((f) => f.evidenceIds).filter(Boolean) ?? []
  }
  const flat = itemFields(item)
  const activeTitleSection = item.books.find(
    (titleExtraction) => printedTitleResultKey(titleExtraction.key) === activeFieldKey,
  )
  const relevantIds = flat.find((field) => field.key === activeFieldKey)?.field.evidenceIds
    ?? (activeTitleSection ? evidenceForTitle(activeTitleSection.key) : undefined)
    ?? []

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

  const acceptAll = (source: string) => {
    for (const ff of adjudicableFields(item)) {
      const c = ff.field.candidates.find((x) => x.source === source)
      if (c) setFieldResult(item.id, ff.key, { choice: source, value: c.value })
    }
  }

  const jumpUnresolved = () => {
    const nextIndex = nextUnresolvedIndex(allQueue, results, allIdx)
    if (nextIndex >= 0) nav(`/item/${allQueue[nextIndex].id}`)
  }

  const leaveInReviewAndNext = () => {
    if (qIdx >= 0 && qIdx + 1 < queue.length) goto(qIdx + 1)
    else jumpUnresolved()
  }

  const completeAndNext = () => {
    if (status === 'done') jumpUnresolved()
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
              {item.subtitle} · {item.books.length} extracted title{item.books.length === 1 ? '' : 's'} · {decided}/{total} decisions
            </span>
            <ItemResearchTags item={item} />
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
          <div className="font-mono text-sm text-slate-200">{allIdx >= 0 ? allIdx + 1 : '–'}/{allQueue.length}</div>
          <StatusDot status={status} />
        </div>
      </header>

      {/* queue sort + backlog selector + research focus */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-800 bg-slate-900/50 px-3 py-1 text-[11px]">
        <span className="text-slate-500">Queue</span>
        <SortChip active={settings.queueMode === 'group'} onClick={() => setSettings({ queueMode: 'group' })}>By backlog</SortChip>
        <SortChip active={settings.queueMode === 'state'} onClick={() => setSettings({ queueMode: 'state' })}>By state</SortChip>
        <SortChip active={settings.queueMode === 'priority'} onClick={() => setSettings({ queueMode: 'priority' })}>Priority</SortChip>
        <span className="text-slate-600">|</span>
        <SortChip active={settings.filter === 'all'} onClick={() => setSettings({ filter: 'all' })}>All</SortChip>
        <SortChip active={settings.filter === 'unresolved'} onClick={() => setSettings({ filter: 'unresolved' })}>Backlog</SortChip>
        <span className="text-slate-600">|</span>
        <span className="text-slate-500">Focus</span>
        {shownFoci.map((focus) => (
          <SortChip key={focus} active={settings.focus === focus} onClick={() => setSettings({ focus })}>
            {FOCUS_LABEL[focus]}
          </SortChip>
        ))}
      </div>

      {/* current bundle falls outside the active focus (e.g. opened from search) */}
      {settings.focus !== 'all' && allIdx < 0 && (
        <div className="flex items-center gap-2 border-b border-slate-800 bg-slate-800/40 px-3 py-1.5 text-[11px] text-slate-400">
          This bundle is outside the “{FOCUS_LABEL[settings.focus]}” focus — next/prev will jump back into it.
          <button
            onClick={() => setSettings({ focus: 'all' })}
            className="rounded bg-slate-700 px-2 py-0.5 text-sky-200 active:bg-slate-600"
          >
            Show all
          </button>
        </div>
      )}

      {/* reviewer instruction banner */}
      {groundTruthAlert(item.alert) && (
        <div className="border-b border-amber-700/40 bg-amber-500/10 px-3 py-2 text-[12px] leading-snug text-amber-200">
          <span className="mr-1">⚠️</span>
          <span className="whitespace-pre-wrap">{groundTruthAlert(item.alert)}</span>
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
          activeFieldKey={activeFieldKey}
          showHighlights={settings.showHighlights}
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
            ⚑ Evidence unavailable / wrong
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

        {[...item.books].sort((a, b) => Number(!!a.optional) - Number(!!b.optional)).map((titleExtraction, titleIndex) => {
          const titleKey = printedTitleResultKey(titleExtraction.key)
          const titleResult = res?.fields?.[titleKey]
          const rejected = titleResult?.choice === CHOICE_NOT_TITLE
          const verb = sectionVerb(titleExtraction)
          const author = titleExtraction.author_as_stated
          const hasOwnDateField = titleExtraction.fields.some((field) => field.key === 'date')
          const titleEvidenceIds = evidenceForTitle(titleExtraction.key)
          return (
          <ClaimSection
            key={titleExtraction.key}
            title={titleExtraction.optional ? `Optional title ${titleIndex + 1}` : `Extracted title ${titleIndex + 1}`}
            badge={titleExtraction.optional ? 'optional — does not block completion' : undefined}
            note={titleExtraction.note}
            kind="title"
          >
            <PrintedTitleRow
              extracted={titleExtraction.title_as_stated}
              result={titleResult}
              optional={titleExtraction.optional}
              onChange={(fieldResult) => setFieldResult(item.id, titleKey, fieldResult)}
              onFocus={() => {
                setActiveFieldKey(titleKey)
                if (titleEvidenceIds[0]) setActiveEvidenceId(titleEvidenceIds[0])
              }}
            />
            {(author || verb) && (
              <div className="flex flex-wrap items-center gap-x-1 text-[11px] leading-snug text-slate-500">
                {author && <span>Author as printed: <span className="text-slate-300">{author}</span></span>}
                {author && verb && <span className="text-slate-700">·</span>}
                {verb && (
                  <VerbChip
                    key={`${item.id}:${titleExtraction.key}`}
                    extracted={verb}
                    sourceName={sourceLabel(verb.source, sourceLabels)}
                    override={res?.verbOverrides?.find((o) => o.sectionKey === titleExtraction.key)?.value ?? null}
                    editable={!rejected}
                    onChange={(value) => setVerbOverride(item.id, titleExtraction.key, value)}
                  />
                )}
              </div>
            )}
            {!rejected && titleExtraction.fields.filter((field) => !isLegacyTitleField(field.key) && !isMetadataField(field.key)).map((f) => {
              const key = resultKey(titleExtraction.key, f.key)
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
            {!rejected && hasEventDate && !hasOwnDateField && (
              <DateOverrideRow
                key={`${item.id}:${titleExtraction.key}`}
                value={res?.dateOverrides?.find((o) => o.sectionKey === titleExtraction.key)?.value ?? null}
                onChange={(value) => setDateOverride(item.id, titleExtraction.key, value)}
              />
            )}
            {rejected && (
              <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                This extraction will be omitted from the corrected title records.
              </p>
            )}
          </ClaimSection>
          )
        })}

        <AddedTitles
          titles={res?.addedTitles ?? []}
          evidence={item.evidence}
          activeEvidenceId={activeEvidenceId}
          onAdd={(value, evidenceId) => addTitle(item.id, { id: newTitleId(), value, evidenceId })}
          onUpdate={(titleId, value) => updateAddedTitle(item.id, titleId, value)}
          onRemove={(titleId) => removeAddedTitle(item.id, titleId)}
        />

        <NotesBox
          value={res?.notes ?? ''}
          placeholder={item.notesPrompt ?? 'notes (optional)…'}
          onChange={(t) => setNotes(item.id, t)}
        />
        <div className="h-24" />
      </div>

      {/* bottom nav */}
      <nav className="flex items-center gap-2 border-t border-slate-800 bg-slate-900/90 px-3 py-2">
        {/* from an out-of-focus item (qIdx -1), Prev re-enters the focused queue at its start */}
        <NavBtn onClick={() => goto(qIdx > 0 ? qIdx - 1 : 0)} disabled={qIdx === 0 || queue.length === 0}>← Prev</NavBtn>
        <NavBtn onClick={leaveInReviewAndNext}>Leave in review &amp; Next</NavBtn>
        <button
          onClick={completeAndNext}
          disabled={status !== 'done'}
          title={status === 'done' ? 'Go to the next unresolved item' : `Resolve ${total - decided} remaining decision${total - decided === 1 ? '' : 's'} first`}
          className="flex-1 rounded-lg bg-sky-600 py-2.5 text-center font-semibold text-white disabled:bg-slate-800 disabled:text-slate-500 active:bg-sky-500"
        >
          {status === 'done' ? 'Complete & Next →' : `${total - decided} unresolved`}
        </button>
        <NavBtn onClick={jumpUnresolved}>⚑</NavBtn>
      </nav>
      </div>{/* /right column */}
      </div>{/* /main two-pane */}

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}

function AddedTitles({
  titles,
  evidence,
  activeEvidenceId,
  onAdd,
  onUpdate,
  onRemove,
}: {
  titles: { id: string; value: string; evidenceId?: string | null }[]
  evidence: { id: string; label: string }[]
  activeEvidenceId: string | null
  onAdd: (value: string, evidenceId: string | null) => void
  onUpdate: (titleId: string, value: string) => void
  onRemove: (titleId: string) => void
}) {
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState('')

  const commit = () => {
    const value = draft.trim()
    if (!value) return
    onAdd(value, activeEvidenceId)
    setDraft('')
    setAdding(false)
  }

  return (
    <div className="mb-3 rounded-xl border border-dashed border-slate-700 bg-slate-900/20 p-3">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="flex-1 text-sm font-semibold text-slate-200">Titles missed by the extraction</h3>
        {!adding && (
          <button onClick={() => setAdding(true)} className="rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs text-slate-200">
            + Add title
          </button>
        )}
      </div>
      {titles.length === 0 && !adding && (
        <p className="text-xs text-slate-500">Add a title only when its words are actually printed in the evidence.</p>
      )}
      <div className="space-y-2">
        {titles.map((title) => (
          <div key={title.id} className="rounded-lg border border-slate-800 bg-slate-900/60 p-2">
            <div className="flex gap-2">
              <label className="min-w-0 flex-1">
                <span className="sr-only">Reviewer-added printed title</span>
                <input
                  value={title.value}
                  onChange={(event) => onUpdate(title.id, event.target.value)}
                  className="w-full bg-transparent px-1 py-1 text-sm text-white outline-none"
                />
              </label>
              <button onClick={() => onRemove(title.id)} className="rounded px-2 text-xs text-rose-300 active:bg-rose-500/10">Remove</button>
            </div>
            {title.evidenceId && (
              <p className="mt-1 text-[10px] text-slate-500">
                Evidence: {evidence.find((item) => item.id === title.evidenceId)?.label ?? title.evidenceId}
              </p>
            )}
          </div>
        ))}
        {adding && (
          <div className="rounded-lg border border-sky-500/40 bg-sky-500/5 p-2">
            <label>
              <span className="sr-only">Title exactly as printed</span>
              <input
                autoFocus
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') commit() }}
                placeholder="title exactly as printed…"
                className="w-full bg-transparent px-1 py-1 text-sm text-white outline-none placeholder:text-slate-500"
              />
            </label>
            <div className="mt-2 flex justify-end gap-2">
              <button onClick={() => { setAdding(false); setDraft('') }} className="rounded px-2 py-1 text-xs text-slate-400">Cancel</button>
              <button onClick={commit} disabled={!draft.trim()} className="rounded bg-sky-600 px-3 py-1 text-xs text-white disabled:opacity-40">Add printed title</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function newTitleId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `added_${Date.now()}_${Math.random().toString(36).slice(2)}`
}

/**
 * The extractor's verb, crystallized — no confirmation needed — but click-to-correct
 * via the controlled vocabulary when the source plainly shows something else.
 */
function VerbChip({
  extracted, sourceName, override, editable, onChange,
}: {
  extracted: { value: string; source: string }
  sourceName: string
  override: string | null
  editable: boolean
  onChange: (v: string | null) => void
}) {
  const [editing, setEditing] = useState(false)
  const effective = override ?? extracted.value
  if (editing) {
    return (
      <label className="inline-flex items-center gap-1">
        <span>source verb:</span>
        <span className="sr-only">Corrected evidence verb</span>
        <select
          autoFocus
          value={effective}
          onChange={(event) => {
            const value = event.target.value
            onChange(value === extracted.value ? null : value)
            setEditing(false)
          }}
          onBlur={() => setEditing(false)}
          className="rounded border border-slate-700 bg-slate-800 px-1 py-0.5 text-[11px] text-slate-200 outline-none"
        >
          {VERB_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option === extracted.value ? `${option} (extractor)` : option}
            </option>
          ))}
        </select>
      </label>
    )
  }
  return (
    <span className="inline-flex items-center gap-1">
      <span>
        source verb: <span className={override ? 'text-sky-300' : 'text-slate-300'}>{effective}</span>{' '}
        <span className="text-slate-600">
          {override ? `(edited — extractor said ${extracted.value})` : `(${sourceName}, no confirmation needed)`}
        </span>
      </span>
      {editable && (
        <button
          type="button"
          onClick={() => setEditing(true)}
          title="Correct the verb"
          className="rounded px-1 text-slate-500 hover:text-slate-300 active:bg-slate-800"
        >
          ✎
        </button>
      )}
      {override && editable && (
        <button
          type="button"
          onClick={() => onChange(null)}
          title="Back to the extractor's verb"
          className="rounded px-1 text-[10px] text-slate-500 underline-offset-2 hover:underline"
        >
          reset
        </button>
      )}
    </span>
  )
}

/**
 * Escape hatch under each title when the bundle uses one event-level date: almost every
 * batch shares one date, so this stays collapsed unless a specific title really differs.
 */
function DateOverrideRow({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) {
  const [draft, setDraft] = useState<string | null>(null)
  const active = draft !== null || value !== null
  if (!active) {
    return (
      <button
        type="button"
        onClick={() => setDraft('')}
        className="text-[11px] text-slate-500 underline-offset-2 hover:underline"
      >
        Date differs for this title…
      </button>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] text-slate-500">Date for this title</span>
      <label className="flex items-center rounded-lg border border-slate-700 bg-slate-800/60">
        <span className="sr-only">Date for this title, exactly as printed</span>
        <input
          value={draft ?? value ?? ''}
          placeholder="as printed…"
          onChange={(event) => {
            setDraft(event.target.value)
            onChange(event.target.value.trim() ? event.target.value : null)
          }}
          className="w-36 bg-transparent px-2 py-1 text-xs text-white outline-none placeholder:text-slate-500"
        />
      </label>
      <button
        type="button"
        onClick={() => { setDraft(null); onChange(null) }}
        className="rounded px-2 py-1 text-[11px] text-rose-300 active:bg-rose-500/10"
      >
        Same as event date
      </button>
    </div>
  )
}

function ClaimSection({
  title, badge, note, kind, children,
}: {
  title: string
  badge?: string
  note?: string
  kind: 'event' | 'title'
  children: ReactNode
}) {
  return (
    <div className={`mb-3 rounded-xl border bg-slate-900/40 p-3 ${badge ? 'border-dashed border-slate-700' : 'border-slate-800'}`}>
      <div className="mb-2 flex flex-wrap items-baseline gap-2">
        <h3 className="text-sm font-semibold text-slate-200">
          <span className="mr-1 text-slate-500">{kind === 'title' ? '“' : '⚖'}</span>
          {title}
        </h3>
        {badge && <span className="rounded bg-slate-700/40 px-1.5 py-0.5 text-[10px] text-slate-400">{badge}</span>}
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
            <b className="text-amber-300">One bundle = one possible adoption event.</b> The extracted titles
            may be incomplete or wrong. Establish only what the page prints; later stages decide canonical
            identity and how the event joins the research data.
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
            <b className="text-amber-300">One date for the whole batch.</b> The event’s <i>Adoption date</i>{' '}
            claim covers every title in the bundle — confirm it once. Only if a specific book prints a
            different date, use <i>Date differs for this title</i> under that book.
          </li>
          <li>
            <b className="text-amber-300">“source verb” is context, not a question.</b> The grey verb/author
            line under a title (adopted, used, …) comes from the extractor and needs no confirmation.
          </li>
          <li>
            <b className="text-amber-300">Follow the evidence chips.</b> Tapping a claim’s label jumps the
            left pane to the page/snippet that claim came from. A ring on a chip means the focused claim
            cites it too.
          </li>
          <li>
            <b className="text-amber-300">Evidence insufficient.</b> Use it when the shipped evidence cannot
            settle the bundle at all (wrong page, illegible scan, link rot). It is not the response for a
            missing or erroneous extraction: overwrite it, mark it “not actually a book title,” or add a
            missed printed title instead. Say what evidence is missing in the notes so the builder can re-cut it.
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
    untouched: 'new', in_progress: 'in review', done: 'complete', insufficient: 'blocked by evidence',
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
