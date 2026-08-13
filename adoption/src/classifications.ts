import type { EvidenceLayout, EvidenceSourceKind, Item } from './types'

/**
 * Project South v1: the 16-state definition in
 * `Adoptions_Enrollment_descriptives.do`, Step 2 (reviewed 2026-08-13).
 * It is intentionally named: this is neither Census South nor only the 11 Confederate states.
 */
export const SOUTHERN_STATES = new Set([
  'AL', 'AR', 'DE', 'FL', 'GA', 'KY', 'LA', 'MD', 'MO',
  'MS', 'NC', 'SC', 'TN', 'TX', 'VA', 'WV',
])

export const SOUTHERN_DEFINITION = 'Project South v1 (16 states)'

/** First statewide/uniform textbook-adoption year in the project's treatment file. */
export const ADOPTION_START_YEAR: Record<string, number> = {
  AL: 1901, AR: 1918, AZ: 1882, DE: 1890, FL: 1905, GA: 1903,
  ID: 1893, IN: 1889, KS: 1897, KY: 1904, LA: 1893, MN: 1873,
  MO: 1891, MS: 1904, MT: 1885, NC: 1901, OK: 1909, OR: 1878,
  SC: 1879, TN: 1899, TX: 1895, VA: 1870, WA: 1877, WV: 1873,
}

export type AdoptionRegime = NonNullable<Item['stateAdoptionRegimeAtEvent']>
export type ResearchFocus =
  | 'all'
  | 'newspapers'
  | 'tables'
  | 'ever_adoption_states'
  | 'southern_states'

/** Static membership only; every UI label using this function says "ever". */
export function isEverAdoptionState(item: Item): boolean {
  return item.state in ADOPTION_START_YEAR
}

/** Prefer builder metadata; the year fallback only keeps older datasets usable. */
export function adoptionRegimeAtEvent(item: Item): AdoptionRegime {
  if (item.stateAdoptionRegimeAtEvent) return item.stateAdoptionRegimeAtEvent
  const start = ADOPTION_START_YEAR[item.state]
  if (!start) return 'not_applicable'
  if (!item.year || item.year < 1700) return 'unknown'
  return item.year >= start ? 'postlaw' : 'prelaw'
}

export function isSouthernState(item: Item): boolean {
  return SOUTHERN_STATES.has(item.state)
}

export function hasSourceKind(item: Item, kind: EvidenceSourceKind): boolean {
  return item.evidence.some((evidence) => evidence.sourceKind === kind)
}

export function hasLayout(item: Item, layout: EvidenceLayout): boolean {
  return item.evidence.some((evidence) => evidence.layout === layout)
}

export function matchesResearchFocus(item: Item, focus: ResearchFocus): boolean {
  if (focus === 'newspapers') return hasSourceKind(item, 'newspaper')
  if (focus === 'tables') return hasLayout(item, 'table') || hasLayout(item, 'mixed')
  if (focus === 'ever_adoption_states') return isEverAdoptionState(item)
  if (focus === 'southern_states') return isSouthernState(item)
  return true
}

export function isPrioritySource(item: Item): boolean {
  return hasSourceKind(item, 'newspaper') || hasLayout(item, 'table') || hasLayout(item, 'mixed')
}

/** Newspaper and table records sort first within their queue. */
export function effectivePriority(item: Item): number {
  return item.priority + (isPrioritySource(item) ? 1 : 0)
}
