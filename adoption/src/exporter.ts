import type { Dataset, Item, ItemResult } from './types'
import { CHOICE_NOT_TITLE } from './types'
import {
  PRINTED_TITLE_FIELD, computeStatus, isLegacyTitleField, isMetadataField, itemFields,
  printedTitleResultKey, sectionVerb,
} from './queue'

/** Full backup — re-importable in Settings (merges by itemId). */
export function buildResultsJSON(dataset: Dataset | null, results: Record<string, ItemResult>) {
  const cleanResults = Object.fromEntries(Object.entries(results).map(([itemId, result]) => [
    itemId,
    {
      ...result,
      fields: Object.fromEntries(Object.entries(result.fields).filter(([key]) => {
        const fieldKey = key.slice(key.lastIndexOf(':') + 1)
        if (isLegacyTitleField(fieldKey) || isMetadataField(fieldKey)) return false
        if (fieldKey === PRINTED_TITLE_FIELD) return true
        const sectionKey = key.slice(0, key.lastIndexOf(':'))
        return result.fields[printedTitleResultKey(sectionKey)]?.choice !== CHOICE_NOT_TITLE
      })),
      addedTitles: result.addedTitles?.filter((title) => title.value.trim()),
      // an override under a rejected false-title row dies with the row, like other dependent fields
      dateOverrides: result.dateOverrides?.filter((override) =>
        override.value.trim()
        && result.fields[printedTitleResultKey(override.sectionKey)]?.choice !== CHOICE_NOT_TITLE),
      verbOverrides: result.verbOverrides?.filter((override) =>
        override.value.trim()
        && result.fields[printedTitleResultKey(override.sectionKey)]?.choice !== CHOICE_NOT_TITLE),
    },
  ]))
  return {
    datasetName: dataset?.meta.name ?? 'unknown',
    schema: 2,
    exportedAt: new Date().toISOString(),
    nResults: Object.keys(cleanResults).length,
    results: cleanResults,
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
    'item_status', 'evidence_insufficient', 'notes', 'record_origin', 'extracted_value', 'evidence_id',
    'extracted_verb', 'extracted_author',
  ]
  const lines = [header.join(',')]
  for (const it of items) {
    const r = results[it.id]
    const status = computeStatus(it, r)
    for (const titleExtraction of it.books) {
      const fr = r?.fields?.[printedTitleResultKey(titleExtraction.key)]
      lines.push([
        it.id, it.group, it.groupKey, it.title, it.subtitle, it.state, it.year,
        titleExtraction.key, titleExtraction.title_as_stated, 'title_as_printed', 'Title as printed',
        fr?.choice ?? '', fr?.value ?? '', fr?.custom ?? '',
        status, r?.insufficient ? 'TRUE' : '', r?.notes ?? '',
        titleExtraction.optional ? 'reextraction_optional' : 'extracted', titleExtraction.title_as_stated, '',
        sectionVerb(titleExtraction)?.value ?? '', titleExtraction.author_as_stated ?? '',
      ].map(csvCell).join(','))
    }
    for (const title of r?.addedTitles?.filter((value) => value.value.trim()) ?? []) {
      lines.push([
        it.id, it.group, it.groupKey, it.title, it.subtitle, it.state, it.year,
        title.id, title.value, 'title_as_printed', 'Title as printed',
        'custom', title.value, title.value,
        status, r?.insufficient ? 'TRUE' : '', r?.notes ?? '', 'reviewer_added', '', title.evidenceId ?? '',
        '', '',
      ].map(csvCell).join(','))
    }
    // rare per-title dates that differ from the confirmed event-level date
    // (suppressed when the title itself was rejected, like other dependent fields)
    for (const override of r?.dateOverrides?.filter((o) =>
      o.value.trim() && r?.fields?.[printedTitleResultKey(o.sectionKey)]?.choice !== CHOICE_NOT_TITLE) ?? []) {
      const section = it.books.find((b) => b.key === override.sectionKey)
      lines.push([
        it.id, it.group, it.groupKey, it.title, it.subtitle, it.state, it.year,
        override.sectionKey, section?.title_as_stated ?? '', 'date_override', 'Date for this title',
        'custom', override.value, override.value,
        status, r?.insufficient ? 'TRUE' : '', r?.notes ?? '', 'reviewer_added', '', '',
        '', '',
      ].map(csvCell).join(','))
    }
    // reviewer corrections of the extractor's verb (same suppression rule)
    for (const override of r?.verbOverrides?.filter((o) =>
      o.value.trim() && r?.fields?.[printedTitleResultKey(o.sectionKey)]?.choice !== CHOICE_NOT_TITLE) ?? []) {
      const section = it.books.find((b) => b.key === override.sectionKey)
      lines.push([
        it.id, it.group, it.groupKey, it.title, it.subtitle, it.state, it.year,
        override.sectionKey, section?.title_as_stated ?? '', 'verb_override', 'Evidence verb (corrected)',
        'custom', override.value, override.value,
        status, r?.insufficient ? 'TRUE' : '', r?.notes ?? '', 'reviewer_added', '',  '',
        section ? sectionVerb(section)?.value ?? '' : '', '',
      ].map(csvCell).join(','))
    }
    for (const ff of itemFields(it)) {
      if (r?.fields?.[printedTitleResultKey(ff.sectionKey)]?.choice === CHOICE_NOT_TITLE) continue
      const fr = r?.fields?.[ff.key]
      lines.push([
        it.id, it.group, it.groupKey, it.title, it.subtitle, it.state, it.year,
        ff.sectionKey, ff.sectionTitle, ff.field.key, ff.field.label,
        fr?.choice ?? '', fr?.value ?? '', fr?.custom ?? '',
        status, r?.insufficient ? 'TRUE' : '', r?.notes ?? '', 'extracted', '', '',
        '', '',
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
