// ---- dataset.json shape (produced by tools/build_adoption_dataset.py — NOT WRITTEN YET) ----
//
// One Item = one ADOPTION EVENT BUNDLE. `books` is retained as the legacy dataset property name,
// but each entry is a printed-title extraction to verify—not a canonical or matched book entity.
// Everything the reviewer needs travels with the item: evidence plus per-extraction source claims.

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

/** Source genre and page layout are deliberately orthogonal. */
export type EvidenceSourceKind = 'newspaper' | 'official_report' | 'minutes' | 'statute' | 'periodical' | 'other'
export type EvidenceLayout = 'prose' | 'table' | 'mixed'

/** A normalized region on the rendered image. All coordinates are in 0..1. */
export interface EvidenceRegion {
  x: number
  y: number
  w: number
  h: number
  kind?: 'passage' | 'row' | 'column' | 'cell'
  label?: string
  /** Result keys supported by this region. Empty/omitted means general context. */
  fieldKeys?: string[]
}

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
  /** Explicit builder metadata. The UI never guesses these tags from prose. */
  sourceKind?: EvidenceSourceKind
  layout?: EvidenceLayout
  /** Stable build provenance, unrelated to canonical-book matching. */
  sourceId?: string
  sourcePath?: string
  page?: { pdfIndex?: number; printedLabel?: string }
  regions?: EvidenceRegion[]
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

/** One proposed literal-title extraction inside the event bundle. */
export interface PrintedTitleSection {
  key: string
  /** the title exactly as it appears in the source, used as the section heading */
  title_as_stated: string
  fields: ClaimField[]
  /** builder note about this extraction (e.g. "the title continues on the next line") */
  note?: string
  /** author exactly as the source prints it — read-only context, not adjudicated */
  author_as_stated?: string
  /** extractor's evidence verb (adopted/used/…) — read-only context, not adjudicated */
  verb?: { value: string; source: string }
  /**
   * Optional section (e.g. a state-history title recovered by re-extraction): decidable
   * but never required — it does not count toward completion or block Complete & Next.
   */
  optional?: boolean
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
  /** Historical statewide-adoption regime at the event date. */
  stateAdoptionRegimeAtEvent?: 'prelaw' | 'postlaw' | 'ambiguous' | 'not_applicable' | 'unknown'
  /** Source cutoff retained for auditability, e.g. "1870-07-11". */
  stateAdoptionCutoff?: string
  /** reviewer instruction shown as a warning banner on the item */
  alert?: string
  /** builder context paragraph shown under the header */
  note?: string
  /** placeholder for the reviewer's notes box */
  notesPrompt?: string
  evidence: EvidenceRef[]
  /** claims about the EVENT itself (date, unit level, statute citation …) — optional */
  eventFields?: ClaimField[]
  /** Legacy transport key; entries are printed-title extractions, not canonical books. */
  books: PrintedTitleSection[]
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
  /** Named geographic classification used for the Southern-state filter. */
  southDefinition?: { id: string; label: string; states: string[] }
}

export interface Dataset { meta: DatasetMeta; items: Item[] }

// ---- adjudication results (stored in IndexedDB, one row per item) ----

/** Reserved choice values — never valid source names. */
export const CHOICE_CUSTOM = 'custom'
export const CHOICE_NOT_STATED = 'not_stated'
export const CHOICE_CANT_TELL = 'cant_tell'
/** The extractor's literal transcription was verified against the page. */
export const CHOICE_EXTRACTED_TITLE = 'extracted_title'
/** The proposed string is not actually a printed book title. */
export const CHOICE_NOT_TITLE = 'not_title'
export const RESERVED_CHOICES: string[] = [
  CHOICE_CUSTOM, CHOICE_NOT_STATED, CHOICE_CANT_TELL, CHOICE_EXTRACTED_TITLE, CHOICE_NOT_TITLE,
]

/** A source name, one of the reserved choices, or null when undecided. Sources are dynamic. */
export type Choice = string | null

export interface FieldResult {
  /** resolved string value (null for not_stated / cant_tell / blank) */
  choice: Choice
  value: string | null
  /** raw text the reviewer typed */
  custom?: string
}

/** A title occurrence the extractor missed and the reviewer transcribed from the page. */
export interface AddedTitleResult {
  id: string
  value: string
  evidenceId?: string | null
}

/**
 * Rare per-title date differing from the event-level date the reviewer confirmed.
 * Optional extra work — never required, never counted toward completion.
 */
export interface DateOverrideResult {
  sectionKey: string
  value: string
}

/**
 * Reviewer correction of the extractor's evidence verb for one title. Like date
 * overrides: optional, never required, never counted toward completion.
 */
export interface VerbOverrideResult {
  sectionKey: string
  value: string
}

/** Evidence-verb vocabulary — mirrors the pipeline's schema.py EVIDENCE_VERBS. */
export const VERB_OPTIONS = [
  'adopted', 'readopted', 'recommended', 'used', 'listed', 'considered', 'rejected', 'conditional',
] as const

export type ItemStatus = 'untouched' | 'in_progress' | 'done' | 'insufficient'

export interface ItemResult {
  itemId: string
  /** keyed by resultKey(sectionKey, fieldKey) — see queue.ts */
  fields: Record<string, FieldResult>
  addedTitles?: AddedTitleResult[]
  dateOverrides?: DateOverrideResult[]
  verbOverrides?: VerbOverrideResult[]
  /** reviewer flagged the bundle as unjudgeable from the evidence shipped */
  insufficient?: boolean
  notes?: string
  status: ItemStatus
  updatedAt: number
}
