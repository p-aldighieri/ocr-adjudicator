import type { Dataset, Item, ItemResult } from './types'
import { adjudicableFields, computeStatus } from './queue'

export function buildResultsJSON(dataset: Dataset | null, results: Record<string, ItemResult>) {
  return {
    datasetName: dataset?.meta.name ?? 'unknown',
    schema: 1,
    exportedAt: new Date().toISOString(),
    nResults: Object.keys(results).length,
    results,
  }
}

function csvCell(v: unknown): string {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** One row per adjudicable field, carrying the chosen value + provenance. */
export function buildResultsCSV(items: Item[], results: Record<string, ItemResult>): string {
  const header = [
    'item_id', 'group_key', 'institution', 'state', 'year', 'n',
    'section', 'field', 'choice', 'value', 'custom_text',
    'item_status', 'wrong_page', 'notes',
  ]
  const lines = [header.join(',')]
  for (const it of items) {
    const r = results[it.id]
    const status = computeStatus(it, r)
    const fieldKeys = new Set(adjudicableFields(it).map((f) => f.key))
    for (const sec of it.sections) {
      for (const f of sec.fields) {
        if (!fieldKeys.has(f.key)) continue
        const fr = r?.fields?.[f.key]
        lines.push([
          it.id, it.groupKey, it.title, it.subtitle, it.year, it.n ?? '',
          sec.key, f.key, fr?.choice ?? '', fr?.value ?? '', fr?.custom ?? '',
          status, r?.wrongPage ? 'TRUE' : '', r?.notes ?? '',
        ].map(csvCell).join(','))
      }
    }
  }
  return lines.join('\n')
}

export function download(filename: string, text: string, mime = 'application/json') {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
