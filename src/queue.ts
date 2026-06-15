import type { Item, ItemResult, ItemStatus, Field } from './types'

export type QueueMode = 'institution' | 'priority'
export type QueueFilter = 'all' | 'unresolved'

export function itemFields(item: Item): Field[] {
  return item.sections.flatMap((s) => s.fields)
}

/** Fields that actually have something to adjudicate (≥1 candidate). */
export function adjudicableFields(item: Item): Field[] {
  return itemFields(item).filter((f) => f.candidates.some((c) => !c.ref))
}

export function decidedCount(item: Item, r?: ItemResult): { decided: number; total: number } {
  const fields = adjudicableFields(item)
  if (!r) return { decided: 0, total: fields.length }
  let decided = 0
  for (const f of fields) {
    const fr = r.fields?.[f.key]
    if (fr && fr.choice) decided++
  }
  return { decided, total: fields.length }
}

export function computeStatus(item: Item, r?: ItemResult): ItemStatus {
  if (r?.wrongPage) return 'wrong_page'
  const { decided, total } = decidedCount(item, r)
  if (total === 0) return 'untouched'
  if (decided === 0) return 'untouched'
  if (decided >= total) return 'done'
  return 'in_progress'
}

export function isResolved(status: ItemStatus): boolean {
  return status === 'done' || status === 'wrong_page'
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
    list.sort((a, b) => b.priority - a.priority || a.group.localeCompare(b.group) || a.year - b.year)
  } else {
    list.sort((a, b) => a.group.localeCompare(b.group) || a.year - b.year)
  }
  return list
}

export interface Progress {
  total: number
  done: number
  inProgress: number
  wrongPage: number
  untouched: number
}

export function overallProgress(items: Item[], results: Record<string, ItemResult>): Progress {
  const p: Progress = { total: items.length, done: 0, inProgress: 0, wrongPage: 0, untouched: 0 }
  for (const it of items) {
    const s = computeStatus(it, results[it.id])
    if (s === 'done') p.done++
    else if (s === 'wrong_page') p.wrongPage++
    else if (s === 'in_progress') p.inProgress++
    else p.untouched++
  }
  return p
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
