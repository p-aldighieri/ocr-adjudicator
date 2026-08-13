/* eslint-disable react-refresh/only-export-components */
import { type ReactNode } from 'react'
import type { ClaimField, FieldResult } from '../types'
import { CHOICE_CANT_TELL, CHOICE_CUSTOM, CHOICE_NOT_STATED } from '../types'

// Sources are dataset-driven, so colours are assigned by position in dataset.meta.sources
// rather than by a hardcoded name map.
const DOTS = [
  'bg-emerald-400', 'bg-amber-400', 'bg-sky-400',
  'bg-violet-400', 'bg-pink-400', 'bg-lime-400', 'bg-orange-400',
]

export function sourceDot(source: string, sources: string[]): string {
  const i = sources.indexOf(source)
  return DOTS[(i < 0 ? sources.length : i) % DOTS.length]
}

export function sourceLabel(source: string, labels: Record<string, string>): string {
  return labels[source] ?? source
}

const FLAG_COLOR: Record<string, TagColor> = {
  weak: 'amber',
  ocr_low: 'amber',
  unreliable: 'red',
  conflict: 'rose',
  inferred: 'violet',
}

export function ClaimRow({
  field,
  sources,
  sourceLabels,
  result,
  suggested,
  onChange,
  onFocus,
  onPick,
}: {
  field: ClaimField
  sources: string[]
  sourceLabels: Record<string, string>
  result?: FieldResult
  suggested: boolean // true => no committed result yet, show field.default as a ghost suggestion
  onChange: (fr: FieldResult) => void
  onFocus: () => void // deliberate: bring this claim's evidence into the pane (label tap)
  onPick: () => void  // highlight this claim only — never moves the evidence pane (value tap / typing)
}) {
  const committed = !!result
  const selChoice = result?.choice ?? (suggested ? field.default : null)
  const customText = result?.choice === CHOICE_CUSTOM ? (result.custom ?? '') : ''

  const options = field.options ?? []

  const pill = (sel: boolean, ghost: boolean) =>
    `rounded-lg px-3 py-2 text-sm border transition ${
      sel
        ? ghost
          ? 'border-dashed border-sky-400 bg-sky-500/10 text-sky-100'
          : 'border-sky-400 bg-sky-500/20 text-white'
        : 'border-slate-700 bg-slate-800/60 text-slate-200 active:bg-slate-700'
    }`

  const choose = (choice: FieldResult['choice'], value: string | null, custom?: string) => {
    onPick() // keep the evidence pane where it is; just highlight this claim
    onChange({ choice, value, custom })
  }

  const customIs = (v: string) => (customText || '').trim().toLowerCase() === v.toLowerCase()

  return (
    <div className="rounded-lg" onClick={onPick}>
      <div className="mb-1 flex flex-wrap items-center gap-2 text-sm text-slate-400">
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onFocus() }}
          title="Show the evidence for this claim"
          className="cursor-pointer underline-offset-2 hover:underline"
        >
          {field.label}
        </button>
        {field.evidenceIds.length > 0 && (
          <span className="text-[10px] text-slate-600">◆ {field.evidenceIds.length}</span>
        )}
        {field.flags?.map((fl) => (
          <Tag key={fl} color={FLAG_COLOR[fl] ?? 'slate'}>{fl.replace(/_/g, ' ')}</Tag>
        ))}
        {field.agree && field.candidates.length >= 2 && <Tag color="emerald">agree</Tag>}
        {!field.agree && field.candidates.length >= 2 && <Tag color="rose">conflict</Tag>}
      </div>

      {field.hint && <p className="mb-1 text-[11px] leading-snug text-slate-500">{field.hint}</p>}

      <div className="flex flex-wrap items-center gap-2">
        {field.candidates.map((c) => {
          const sel = selChoice === c.source
          return (
            <button key={c.source} className={pill(sel, sel && !committed)} onClick={() => choose(c.source, c.value)}>
              <span className={`mr-1 inline-block h-2 w-2 rounded-full ${sourceDot(c.source, sources)}`} />
              <span className="font-medium">{c.value || <i className="text-slate-500">blank</i>}</span>
              <span className="ml-1 text-[11px] text-slate-400">{sourceLabel(c.source, sourceLabels)}</span>
            </button>
          )
        })}
        {field.candidates.length === 0 && (
          <span className="text-xs italic text-slate-500">no proposal — read it off the evidence or mark not stated</span>
        )}

        {/* type my own */}
        <div className={`flex items-center rounded-lg border ${selChoice === CHOICE_CUSTOM ? 'border-sky-400 bg-sky-500/15' : 'border-slate-700 bg-slate-800/60'}`}>
          <input
            inputMode="text"
            placeholder={field.valueType === 'text' ? 'type as printed…' : 'other…'}
            value={customText}
            onFocus={onPick}
            onChange={(e) => {
              const t = e.target.value
              choose(CHOICE_CUSTOM, t.trim() === '' ? null : t.trim(), t)
            }}
            className={`bg-transparent px-2 py-2 text-sm text-white outline-none placeholder:text-slate-500 ${
              field.valueType === 'text' ? 'w-56' : 'w-28'
            }`}
          />
        </div>

        {/* not stated: the source simply does not say */}
        <button
          className={pill(selChoice === CHOICE_NOT_STATED, false) + ' text-slate-200'}
          onClick={() => choose(CHOICE_NOT_STATED, null)}
        >
          Not stated
        </button>

        {/* can't tell: it is there but illegible / ambiguous */}
        <button
          className={pill(selChoice === CHOICE_CANT_TELL, false) + ' text-rose-200'}
          onClick={() => choose(CHOICE_CANT_TELL, null)}
        >
          Can’t tell
        </button>
      </div>

      {/* controlled vocabulary for 'choice' claims — anything not already offered as a candidate */}
      {field.valueType === 'choice' && options.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {options
            .filter((o) => !field.candidates.some((c) => c.value === o))
            .map((o) => (
              <button
                key={o}
                className={`rounded-full px-2.5 py-1 text-[11px] ${
                  selChoice === CHOICE_CUSTOM && customIs(o)
                    ? 'bg-sky-600 text-white'
                    : 'bg-slate-800 text-slate-300 active:bg-slate-700'
                }`}
                onClick={() => choose(CHOICE_CUSTOM, o, o)}
              >
                {o}
              </button>
            ))}
        </div>
      )}

      {field.candidates.some((c) => c.note) && (
        <div className="mt-1 space-y-0.5 text-[11px] leading-snug text-slate-500">
          {field.candidates.filter((c) => c.note).map((c) => (
            <div key={c.source}>
              <span className="text-slate-400">{sourceLabel(c.source, sourceLabels)}:</span> {c.note}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

type TagColor = 'amber' | 'red' | 'emerald' | 'rose' | 'violet' | 'slate'

function Tag({ children, color }: { children: ReactNode; color: TagColor }) {
  const map: Record<TagColor, string> = {
    amber: 'bg-amber-500/15 text-amber-300',
    red: 'bg-red-500/15 text-red-300',
    emerald: 'bg-emerald-500/15 text-emerald-300',
    rose: 'bg-rose-500/15 text-rose-300',
    violet: 'bg-violet-500/15 text-violet-300',
    slate: 'bg-slate-500/15 text-slate-300',
  }
  return <span className={`rounded px-1.5 py-0.5 text-[10px] ${map[color]}`}>{children}</span>
}
