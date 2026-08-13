import type { ClaimField, FieldResult, Item, ItemResult, ItemStatus, QueueGroup } from './types'
import { CHOICE_CUSTOM, CHOICE_NOT_TITLE, QUEUE_GROUPS } from './types'
import { effectivePriority } from './classifications'

export type QueueMode = 'group' | 'state' | 'priority'
export type QueueFilter = 'all' | 'unresolved'

/** Section key used for claims about the event itself (Item.eventFields). */
export const EVENT_SECTION = '_event'
export const EVENT_SECTION_TITLE = 'This adoption event'
/** Synthetic result field used to adjudicate PrintedTitleSection.title_as_stated itself. */
export const PRINTED_TITLE_FIELD = 'title_as_printed'
/** Legacy fields that conflate literal extraction with downstream canonical matching. */
export const LEGACY_BOOK_MATCH_FIELD = 'book_match'
export const LEGACY_PRINTED_TITLE_FIELD = 'title'

export function isLegacyTitleField(fieldKey: string): boolean {
  return fieldKey === LEGACY_BOOK_MATCH_FIELD || fieldKey === LEGACY_PRINTED_TITLE_FIELD
}

/**
 * Result keys are namespaced by section: the same field key (title, publisher, subject…)
 * repeats in every title extraction of a bundle, so a flat `field.key` would collide.
 */
export function resultKey(sectionKey: string, fieldKey: string): string {
  return `${sectionKey}:${fieldKey}`
}

export function printedTitleResultKey(sectionKey: string): string {
  return resultKey(sectionKey, PRINTED_TITLE_FIELD)
}

export interface FlatField {
  sectionKey: string
  sectionTitle: string
  field: ClaimField
  /** resultKey(sectionKey, field.key) */
  key: string
}

/** Every claim in the bundle, event claims first, then printed-title extraction by extraction. */
export function itemFields(item: Item): FlatField[] {
  const out: FlatField[] = []
  for (const f of item.eventFields ?? []) {
    out.push({ sectionKey: EVENT_SECTION, sectionTitle: EVENT_SECTION_TITLE, field: f, key: resultKey(EVENT_SECTION, f.key) })
  }
  for (const b of item.books) {
    for (const f of b.fields) {
      if (isLegacyTitleField(f.key)) continue
      out.push({ sectionKey: b.key, sectionTitle: b.title_as_stated, field: f, key: resultKey(b.key, f.key) })
    }
  }
  return out
}

/** Claims that carry at least one machine/registry proposal. */
export function adjudicableFields(item: Item): FlatField[] {
  return itemFields(item).filter((f) => f.field.candidates.length > 0)
}

/** Source names that actually appear somewhere in this bundle (drives the "accept all" row). */
export function itemSources(item: Item): string[] {
  const seen = new Set<string>()
  for (const { field } of itemFields(item)) for (const c of field.candidates) seen.add(c.source)
  return [...seen]
}

function isDecided(result?: FieldResult): boolean {
  if (!result?.choice) return false
  if (result.choice === CHOICE_CUSTOM) return !!result.value?.trim()
  return true
}

export function decidedCount(item: Item, r?: ItemResult): { decided: number; total: number } {
  let decided = 0
  let total = 0

  for (const field of item.eventFields ?? []) {
    total++
    if (isDecided(r?.fields?.[resultKey(EVENT_SECTION, field.key)])) decided++
  }

  for (const titleExtraction of item.books) {
    const titleResult = r?.fields?.[printedTitleResultKey(titleExtraction.key)]
    total++
    if (isDecided(titleResult)) decided++

    // Rejecting a false-positive title also rejects its dependent title-level claims.
    if (titleResult?.choice === CHOICE_NOT_TITLE) continue
    for (const field of titleExtraction.fields) {
      if (isLegacyTitleField(field.key)) continue
      total++
      if (isDecided(r?.fields?.[resultKey(titleExtraction.key, field.key)])) decided++
    }
  }

  const added = r?.addedTitles?.filter((title) => title.value.trim()).length ?? 0
  return { decided: decided + added, total: total + added }
}

/** Remove alerts created solely by the downstream canonical-matching pass. */
export function groundTruthAlert(alert?: string): string | null {
  if (!alert) return null
  const out = alert
    .replace(/at least one title has no confident book match;?\s*/gi, '')
    .replace(/Read the evidence before choosing:\s*(?=\.|$)/i, '')
    .replace(/\s+\./g, '.')
    .replace(/^\s*[;.]+\s*/, '')
    .trim()
  return out || null
}

export function computeStatus(item: Item, r?: ItemResult): ItemStatus {
  if (r?.insufficient) return 'insufficient'
  const { decided, total } = decidedCount(item, r)
  if (total === 0) return 'untouched'
  if (decided === 0) return 'untouched'
  if (decided >= total) return 'done'
  return 'in_progress'
}

export function isResolved(status: ItemStatus): boolean {
  return status === 'done' || status === 'insufficient'
}

const GROUP_ORDER: Record<QueueGroup, number> = {
  new_records: 0,
  conflicts: 1,
  state_laws: 2,
}

function byGroup(a: Item, b: Item): number {
  return (GROUP_ORDER[a.group] ?? 99) - (GROUP_ORDER[b.group] ?? 99)
}

export function buildQueue(
  items: Item[],
  results: Record<string, ItemResult>,
  mode: QueueMode,
  filter: QueueFilter,
): Item[] {
  let list = [...items]
  if (filter === 'unresolved') {
    list = list.filter((it) => !isResolved(computeStatus(it, results[it.id])))
  }
  if (mode === 'priority') {
    list.sort((a, b) => effectivePriority(b) - effectivePriority(a) || byGroup(a, b) || a.year - b.year)
  } else if (mode === 'state') {
    // geographic: one state end to end, chronologically
    list.sort((a, b) => a.state.localeCompare(b.state) || a.year - b.year || byGroup(a, b))
  } else {
    // by backlog: clear new records, then conflicts, then state laws
    list.sort((a, b) => byGroup(a, b) || effectivePriority(b) - effectivePriority(a) || a.state.localeCompare(b.state) || a.year - b.year)
  }
  return list
}

export interface Progress {
  total: number
  done: number
  inProgress: number
  insufficient: number
  untouched: number
}

export function overallProgress(items: Item[], results: Record<string, ItemResult>): Progress {
  const p: Progress = { total: items.length, done: 0, inProgress: 0, insufficient: 0, untouched: 0 }
  for (const it of items) {
    const s = computeStatus(it, results[it.id])
    if (s === 'done') p.done++
    else if (s === 'insufficient') p.insufficient++
    else if (s === 'in_progress') p.inProgress++
    else p.untouched++
  }
  return p
}

export function progressByGroup(
  items: Item[],
  results: Record<string, ItemResult>,
): Record<QueueGroup, Progress> {
  const out = {} as Record<QueueGroup, Progress>
  for (const g of QUEUE_GROUPS) out[g] = overallProgress(items.filter((i) => i.group === g), results)
  return out
}

/** Index of the next unresolved item in `queue` after `fromIdx` (wraps around). */
export function nextUnresolvedIndex(
  queue: Item[],
  results: Record<string, ItemResult>,
  fromIdx: number,
): number {
  const n = queue.length
  for (let step = 1; step <= n; step++) {
    const i = (fromIdx + step) % n
    if (!isResolved(computeStatus(queue[i], results[queue[i].id]))) return i
  }
  return -1
}
