// ---- dataset.json shape (produced by tools/build_adoption_dataset.py — NOT WRITTEN YET) ----
//
// One Item = one ADOPTION EVENT BUNDLE: a single board action / statute that adopted one or
// more books. Everything the reviewer needs to judge that event travels with the item:
// the evidence (scans, rendered PDF pages, transcripts, stable URLs) and the per-book claims.

/** Review backlog an item belongs to. Fixed set — the Overview renders one section per group. */
export type QueueGroup = 'new_records' | 'conflicts' | 'state_laws'

export const QUEUE_GROUPS: QueueGroup[] = ['new_records', 'conflicts', 'state_laws']

export const GROUP_LABEL: Record<QueueGroup, string> = {
  new_records: 'New records',
  conflicts: 'Conflicts',
  state_laws: 'State laws',
}

/**
 * How a piece of evidence is displayed:
 *  - 'image'    — a scan/crop shipped as an asset (zoom-pan viewer)
 *  - 'pdf_page' — one page of a PDF rendered to an image asset by the builder (same viewer)
 *  - 'text'     — an inline snippet / transcript, shown verbatim in a monospace block
 *  - 'url'      — an external stable link (HathiTrust, Chronicling America, archive.org …)
 */
export type EvidenceRole = 'image' | 'pdf_page' | 'text' | 'url'

export interface EvidenceRef {
  id: string
  role: EvidenceRole
  /** relative asset path under the dataset root, e.g. "assets/al_1901_minutes.webp" (image | pdf_page) */
  file?: string
  /** inline snippet or transcript (text role; may also annotate an image) */
  text?: string
  /** external stable URL (url role) */
  href?: string
  /** short chip label, e.g. "Minutes p. 214" */
  label: string
  /** citation string shown under the evidence: document / page / date */
  sourceLine: string
}

/**
 * 'choice' — the value comes from a controlled vocabulary (`options`); the custom box is a
 *            narrow escape hatch for values the vocabulary misses.
 * 'text'   — free text transcribed as printed (titles, publishers, citations).
 */
export type ValueType = 'choice' | 'text'

/**
 * One proposed value for a claim. `source` is DYNAMIC — whatever the builder puts in
 * dataset.meta.sources (models, registries, prior-round humans, heuristics). Never hardcode
 * the set. Reserved names ('custom', 'not_stated', 'cant_tell') must not be used as sources.
 */
export interface Candidate {
  source: string
  value: string
  /** why this source proposed it / what it hedged on — rendered under the pill row */
  note?: string
}

export interface ClaimField {
  key: string
  label: string
  valueType: ValueType
  candidates: Candidate[]
  /** source name to pre-select as a ghost suggestion (null = no default) */
  default: string | null
  /** true when every candidate agrees — drives the agree/conflict tag */
  agree: boolean
  /** ids of the EvidenceRefs that back this claim — tapping the label focuses the first */
  evidenceIds: string[]
  /** free-form builder flags, e.g. ['weak', 'unreliable', 'ocr_low'] — rendered as tags */
  flags: string[]
  /** controlled vocabulary offered as secondary pills (valueType 'choice') */
  options?: string[]
  /** one-line reviewer instruction shown under the label */
  hint?: string
}

/** One adopted book inside the event bundle. */
export interface BookSection {
  key: string
  /** the title exactly as it appears in the source, used as the section heading */
  title_as_stated: string
  fields: ClaimField[]
  /** builder note about this book (e.g. "listed twice in the minutes") */
  note?: string
}

export interface Item {
  id: string
  /** event key — everything sharing it is the same board action (state|unit|date) */
  groupKey: string
  group: QueueGroup
  /** e.g. "Baldwin County board — 1901-09-20" */
  title: string
  /** state / county line, e.g. "Baldwin County, Alabama" */
  subtitle: string
  /** two-letter state code */
  state: string
  year: number
  /** 0..1, higher = review sooner */
  priority: number
  /** reviewer instruction shown as a warning banner on the item */
  alert?: string
  /** builder context paragraph shown under the header */
  note?: string
  /** placeholder for the reviewer's notes box */
  notesPrompt?: string
  evidence: EvidenceRef[]
  /** claims about the EVENT itself (date, unit level, statute citation …) — optional */
  eventFields?: ClaimField[]
  books: BookSection[]
}

export interface DatasetMeta {
  name: string
  schema: number
  note?: string
  states: string[]
  years: number[]
  nItems: number
  /** candidate source names in display order — the UI derives every label/colour from this */
  sources: string[]
  /** pretty names for sources; falls back to the raw source name */
  sourceLabels?: Record<string, string>
}

export interface Dataset { meta: DatasetMeta; items: Item[] }

// ---- adjudication results (stored in IndexedDB, one row per item) ----

/** Reserved choice values — never valid source names. */
export const CHOICE_CUSTOM = 'custom'
export const CHOICE_NOT_STATED = 'not_stated'
export const CHOICE_CANT_TELL = 'cant_tell'
export const RESERVED_CHOICES: string[] = [CHOICE_CUSTOM, CHOICE_NOT_STATED, CHOICE_CANT_TELL]

/** A source name, one of the reserved choices, or null when undecided. Sources are dynamic. */
export type Choice = string | null

export interface FieldResult {
  /** resolved string value (null for not_stated / cant_tell / blank) */
  choice: Choice
  value: string | null
  /** raw text the reviewer typed */
  custom?: string
}

export type ItemStatus = 'untouched' | 'in_progress' | 'done' | 'insufficient'

export interface ItemResult {
  itemId: string
  /** keyed by resultKey(sectionKey, fieldKey) — see queue.ts */
  fields: Record<string, FieldResult>
  /** reviewer flagged the bundle as unjudgeable from the evidence shipped */
  insufficient?: boolean
  notes?: string
  status: ItemStatus
  updatedAt: number
}
