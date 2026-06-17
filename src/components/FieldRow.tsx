import { useEffect, useState } from 'react'
import type { Field, FieldResult } from '../types'

const SRC_LABEL: Record<string, string> = {
  claude: 'Claude', codex: 'Codex', current: 'Current', landgrant: 'Land-grant', quincy: 'Quincy',
}
const SRC_DOT: Record<string, string> = {
  claude: 'bg-emerald-400', codex: 'bg-amber-400', current: 'bg-sky-400',
}

export function FieldRow({
  field,
  result,
  suggested,
  onChange,
  onFocus,
  onPick,
}: {
  field: Field
  result?: FieldResult
  suggested: boolean // true => no committed result yet, show field.default as a ghost suggestion
  onChange: (fr: FieldResult) => void
  onFocus: () => void // deliberate: bring this field's image into the viewer (label tap)
  onPick: () => void  // highlight this field only — never moves the viewer (value tap / typing)
}) {
  const committed = !!result
  const selChoice = result?.choice ?? (suggested ? field.default : null)
  const selCustom = result?.choice === 'custom' ? (result.custom ?? '') : ''
  const [customText, setCustomText] = useState(selCustom)
  useEffect(() => { setCustomText(result?.choice === 'custom' ? (result.custom ?? '') : '') }, [result, field.key])

  const pickable = field.candidates.filter((c) => !c.ref)
  const refs = field.candidates.filter((c) => c.ref)

  const pill = (sel: boolean, ghost: boolean) =>
    `rounded-lg px-3 py-2 text-sm border transition ${
      sel
        ? ghost
          ? 'border-dashed border-sky-400 bg-sky-500/10 text-sky-100'
          : 'border-sky-400 bg-sky-500/20 text-white'
        : 'border-slate-700 bg-slate-800/60 text-slate-200 active:bg-slate-700'
    }`

  const choose = (choice: FieldResult['choice'], value: number | null, custom?: string) => {
    onPick() // keep the viewer where it is; just highlight this field's box
    onChange({ choice, value, custom })
  }

  return (
    <div className="rounded-lg" onClick={onPick}>
      <div className="mb-1 flex items-center gap-2 text-sm text-slate-400">
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onFocus() }}
          title="Show this value on the scan"
          className="cursor-pointer underline-offset-2 hover:underline"
        >
          {field.label}
        </button>
        {field.flags?.includes('weak') && <Tag color="amber">weak col</Tag>}
        {field.flags?.includes('unreliable') && <Tag color="red">unreliable</Tag>}
        {field.agree && pickable.length >= 2 && <Tag color="emerald">agree</Tag>}
        {!field.agree && pickable.length >= 2 && <Tag color="rose">conflict</Tag>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {pickable.map((c) => {
          const sel = selChoice === c.source
          return (
            <button key={c.source} className={pill(sel, sel && !committed)} onClick={() => choose(c.source as FieldResult['choice'], c.value)}>
              <span className={`mr-1 inline-block h-2 w-2 rounded-full ${SRC_DOT[c.source] ?? 'bg-violet-400'}`} />
              <span className="font-mono">{c.value}</span>
              <span className="ml-1 text-[11px] text-slate-400">{SRC_LABEL[c.source] ?? c.source}</span>
            </button>
          )
        })}
        {pickable.length === 0 && <span className="text-xs italic text-slate-500">no value extracted</span>}

        {/* type my own */}
        <div className={`flex items-center rounded-lg border ${selChoice === 'custom' ? 'border-sky-400 bg-sky-500/15' : 'border-slate-700 bg-slate-800/60'}`}>
          <input
            inputMode="text"
            placeholder="mine / N/A"
            value={customText}
            onFocus={onPick}
            onChange={(e) => {
              const t = e.target.value
              setCustomText(t)
              const n = t.trim() === '' ? null : Number(t.replace(/[, ]/g, ''))
              choose('custom', Number.isFinite(n as number) ? (n as number) : null, t)
            }}
            className="w-24 bg-transparent px-2 py-2 text-sm text-white outline-none placeholder:text-slate-500"
          />
        </div>

        {/* N/A: value genuinely not printed in the source */}
        <button
          className={pill(selChoice === 'custom' && (customText || '').trim().toUpperCase() === 'N/A', false) + ' text-slate-200'}
          onClick={() => { setCustomText('N/A'); choose('custom', null, 'N/A') }}
        >
          N/A
        </button>

        {/* can't read: value is there but illegible */}
        <button
          className={pill(selChoice === 'cant_read', false) + ' text-rose-200'}
          onClick={() => choose('cant_read', null)}
        >
          Can’t read
        </button>
      </div>

      {refs.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500">
          {refs.map((r) => (
            <button
              key={r.source}
              className="rounded bg-slate-800/50 px-2 py-0.5 hover:text-slate-300"
              onClick={() => { setCustomText(String(r.value)); choose('custom', r.value, String(r.value)) }}
            >
              ref · {SRC_LABEL[r.source] ?? r.source}: <span className="font-mono">{r.value}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function Tag({ children, color }: { children: React.ReactNode; color: 'amber' | 'red' | 'emerald' | 'rose' }) {
  const map = {
    amber: 'bg-amber-500/15 text-amber-300',
    red: 'bg-red-500/15 text-red-300',
    emerald: 'bg-emerald-500/15 text-emerald-300',
    rose: 'bg-rose-500/15 text-rose-300',
  }
  return <span className={`rounded px-1.5 py-0.5 text-[10px] ${map[color]}`}>{children}</span>
}
