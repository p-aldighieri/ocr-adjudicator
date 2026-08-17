import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../store'
import { clearOpfsDataset, importDatasetZip } from '../dataset'
import { buildResultsCSV, buildResultsJSON, download } from '../exporter'
import { db } from '../db'

export function Settings({ embedded = false }: { embedded?: boolean }) {
  const nav = useNavigate()
  const { dataset, items, results, settings, setSettings, source, reload, importResults } = useStore()
  const fileRef = useRef<HTMLInputElement>(null)
  const freshFileRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const reviewCells = items.reduce(
    (total, item) => total + item.sections.reduce((n, section) => n + section.fields.length, 0),
    0,
  )

  const importResultsFile = async (file: File) => {
    setBusy('Restoring adjudications…')
    try {
      const n = await importResults(JSON.parse(await file.text()))
      setBusy(`Restored ${n} record${n === 1 ? '' : 's'}.`)
    } catch (e) {
      setBusy(`Import failed: ${String(e)}`)
    }
  }

  const importZip = async (file: File, clearOldAnswers = false) => {
    setBusy(clearOldAnswers ? 'Importing new dataset before clearing old answers…' : 'Importing dataset…')
    try {
      await importDatasetZip(file, (d, t) => setBusy(`Importing ${d}/${t}…`))
      if (clearOldAnswers) {
        setBusy('Dataset imported. Clearing old answers…')
        await db.results.clear()
      }
      await reload()
      setBusy(clearOldAnswers ? 'New review is ready. Old dataset and answers were cleared.' : 'Dataset imported.')
      if (embedded) nav('/overview')
    } catch (e) {
      setBusy(`Import failed: ${String(e)}`)
    }
  }

  const exportJSON = () =>
    download('adjudications.json', JSON.stringify(buildResultsJSON(dataset, results), null, 2))
  const exportCSV = () =>
    download('adjudications.csv', buildResultsCSV(items, results), 'text/csv')

  return (
    <div className="flex h-full flex-col">
      {!embedded && (
        <header className="flex items-center gap-2 border-b border-slate-800 bg-slate-900/80 px-3 py-2">
          <button onClick={() => nav('/overview')} className="rounded px-2 py-1 text-slate-300 active:bg-slate-800">←</button>
          <h1 className="text-base font-semibold text-white">Settings</h1>
        </header>
      )}

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {!embedded && (
          <>
            <Section title="Queue">
              <Toggle label="Order" value={settings.queueMode} options={[['institution', 'By institution'], ['year', 'By year'], ['priority', 'Priority']]} onChange={(v) => setSettings({ queueMode: v as never })} />
              <Toggle label="Show" value={settings.filter} options={[['all', 'All'], ['unresolved', 'Unresolved only']]} onChange={(v) => setSettings({ filter: v as never })} />
            </Section>

            <Section title="Overlays">
              <Check label="Show value boxes" checked={settings.showOverlays} onChange={(v) => setSettings({ showOverlays: v })} />
              <Check label="Show row highlight" checked={settings.showRow} onChange={(v) => setSettings({ showRow: v })} />
            </Section>

            <Section title="Export & backup">
              <p className="mb-2 text-xs text-slate-500">
                Export to move your work to a computer. <b>Export JSON</b> is a full backup — re-import it
                here to restore your progress after reinstalling or on another device. CSV is one row per value.
              </p>
              <div className="flex flex-wrap gap-2">
                <Btn onClick={exportJSON}>Export JSON</Btn>
                <Btn onClick={exportCSV}>Export CSV</Btn>
                <input ref={resultsRef} type="file" accept=".json,application/json" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) void importResultsFile(f) }} />
                <Btn onClick={() => resultsRef.current?.click()}>Import adjudications (JSON)</Btn>
              </div>
              {busy && <p className="mt-2 text-xs text-sky-300">{busy}</p>}
              <p className="mt-2 text-[11px] text-slate-600">
                Importing merges by record — it restores saved answers without erasing others.
                Done so far: {Object.keys(results).length}.
              </p>
            </Section>
          </>
        )}

        <Section title="Dataset">
          <div className="mb-3 rounded-lg border border-sky-900/70 bg-sky-950/30 p-3 text-xs text-slate-300">
            <p className="font-semibold text-sky-200">Starting Aadhav's new review</p>
            <ol className="mt-1 list-decimal space-y-1 pl-4 text-slate-400">
              <li>If the old work matters, export its JSON backup first.</li>
              <li>Click <b className="text-slate-200">Start fresh &amp; import new .zip</b>.</li>
              <li>Select the new ZIP. The app replaces the old dataset and clears its saved answers after the import succeeds.</li>
            </ol>
          </div>
          <p className="mb-2 text-xs text-slate-500">
            Source: <span className="text-slate-300">{source ?? 'none'}</span>
            {dataset && <> · {dataset.meta.name} · {items.length} universities · {reviewCells} cells</>}
          </p>
          <input ref={fileRef} type="file" accept=".zip" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void importZip(f); e.target.value = '' }} />
          <input ref={freshFileRef} type="file" accept=".zip" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void importZip(f, true); e.target.value = '' }} />
          <div className="flex flex-wrap gap-2">
            <Btn onClick={() => {
              if (confirm('Start a clean review? After the new ZIP imports successfully, the current dataset and ALL saved adjudications will be replaced. Export JSON first if you need a backup.')) {
                freshFileRef.current?.click()
              }
            }}>Start fresh &amp; import new .zip</Btn>
            <Btn onClick={() => fileRef.current?.click()}>Replace dataset, keep answers</Btn>
            {source === 'opfs' && (
              <Btn danger onClick={async () => { await clearOpfsDataset(); await reload() }}>Remove imported dataset</Btn>
            )}
          </div>
          {busy && <p className="mt-2 text-xs text-sky-300">{busy}</p>}
        </Section>

        {!embedded && (
          <Section title="Danger zone">
            <Btn danger onClick={async () => {
              if (confirm('Delete ALL your adjudications? This cannot be undone (export first).')) {
                await db.results.clear(); await reload()
              }
            }}>Clear all adjudications</Btn>
          </Section>
        )}
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
      <h2 className="mb-2 text-sm font-semibold text-slate-200">{title}</h2>
      {children}
    </div>
  )
}
function Btn({ children, onClick, danger }: { children: React.ReactNode; onClick: () => void; danger?: boolean }) {
  return (
    <button onClick={onClick} className={`rounded-lg px-3 py-2 text-sm ${danger ? 'bg-rose-700 text-white active:bg-rose-600' : 'bg-slate-700 text-white active:bg-slate-600'}`}>
      {children}
    </button>
  )
}
function Toggle({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span className="w-16 text-xs text-slate-400">{label}</span>
      <div className="flex gap-1">
        {options.map(([v, l]) => (
          <button key={v} onClick={() => onChange(v)} className={`rounded-lg px-3 py-1.5 text-xs ${value === v ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300'}`}>{l}</button>
        ))}
      </div>
    </div>
  )
}
function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="mb-1 flex items-center gap-2 text-sm text-slate-300">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 accent-sky-500" />
      {label}
    </label>
  )
}
