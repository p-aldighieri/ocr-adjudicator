import type { FieldResult } from '../types'
import { CHOICE_CUSTOM, CHOICE_EXTRACTED_TITLE, CHOICE_NOT_TITLE } from '../types'

export function PrintedTitleRow({
  extracted,
  result,
  optional,
  onChange,
  onFocus,
}: {
  extracted: string
  result?: FieldResult
  optional?: boolean
  onChange: (result: FieldResult) => void
  onFocus: () => void
}) {
  const choice = result?.choice ?? null
  const correction = choice === CHOICE_CUSTOM ? (result?.custom ?? '') : ''
  const pill = (selected: boolean) => `rounded-lg border px-3 py-2 text-left text-sm transition ${
    selected
      ? 'border-sky-400 bg-sky-500/20 text-white'
      : 'border-slate-700 bg-slate-800/60 text-slate-200 active:bg-slate-700'
  }`

  return (
    <div className="rounded-lg">
      <div className="mb-1 flex items-center gap-2 text-sm text-slate-400">
        <button type="button" onClick={onFocus} className="underline-offset-2 hover:underline">
          Title as printed
        </button>
        {!result && !optional && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">needs review</span>}
      </div>
      <p className="mb-2 text-[11px] leading-snug text-slate-500">
        Check only the words visible on the page. Canonical-book identification happens later.
      </p>
      <div className="flex flex-col gap-2">
        <button
          type="button"
          className={pill(choice === CHOICE_EXTRACTED_TITLE)}
          onClick={() => onChange({ choice: CHOICE_EXTRACTED_TITLE, value: extracted })}
        >
          <span className="mr-1 text-[11px] text-slate-400">Use extraction:</span>
          <span className="font-medium">{extracted || <i className="text-slate-500">blank</i>}</span>
        </button>
        <label className={`flex items-center rounded-lg border ${choice === CHOICE_CUSTOM ? 'border-sky-400 bg-sky-500/15' : 'border-slate-700 bg-slate-800/60'}`}>
          <span className="sr-only">Overwrite with title exactly as printed</span>
          <input
            type="text"
            value={correction}
            placeholder="overwrite with the title exactly as printed…"
            onFocus={onFocus}
            onChange={(event) => {
              const value = event.target.value
              onChange({ choice: CHOICE_CUSTOM, value: value.trim() || null, custom: value })
            }}
            className="w-full bg-transparent px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500"
          />
        </label>
        <button
          type="button"
          className={`${pill(choice === CHOICE_NOT_TITLE)} text-rose-200`}
          onClick={() => onChange({ choice: CHOICE_NOT_TITLE, value: null })}
        >
          Not actually a book title
        </button>
      </div>
    </div>
  )
}
