import type { Dataset, Item, ItemResult } from './types'
import { computeStatus, itemFields } from './queue'

/** Full backup — re-importable in Settings (merges by itemId). */
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

/**
 * One row per claim — including claims with no candidates, since the reviewer can type values
 * the pipeline missed (dropping them here silently loses that work).
 */
export function buildResultsCSV(items: Item[], results: Record<string, ItemResult>): string {
  const header = [
    'item_id', 'group', 'group_key', 'title', 'subtitle', 'state', 'year',
    'section', 'section_title', 'field', 'field_label',
    'choice', 'value', 'custom_text',
    'item_status', 'evidence_insufficient', 'notes',
  ]
  const lines = [header.join(',')]
  for (const it of items) {
    const r = results[it.id]
    const status = computeStatus(it, r)
    for (const ff of itemFields(it)) {
      const fr = r?.fields?.[ff.key]
      lines.push([
        it.id, it.group, it.groupKey, it.title, it.subtitle, it.state, it.year,
        ff.sectionKey, ff.sectionTitle, ff.field.key, ff.field.label,
        fr?.choice ?? '', fr?.value ?? '', fr?.custom ?? '',
        status, r?.insufficient ? 'TRUE' : '', r?.notes ?? '',
      ].map(csvCell).join(','))
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
