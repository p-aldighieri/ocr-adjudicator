// ---- dataset.json shape (produced by tools/build_dataset.py) ----
export interface BBox { field: string; source: string; x: number; y: number; w: number; h: number }
export interface RowBand { y: number; h: number }
export interface Overlay { row: RowBand | null; boxes: BBox[] }

export interface ImageRef {
  id: string
  file: string
  w: number          // ORIGINAL pixel size (overlay coords are normalized to this)
  h: number
  role: 'snippet' | 'full'
  side: string
  label: string
}

export interface Candidate { source: string; value: number; ref?: boolean }

export interface Field {
  key: string
  label: string
  imageId: string | null
  candidates: Candidate[]
  agree: boolean
  default: string | null
  flags: string[]
  confident?: boolean
  unit?: string
}

export interface Section { key: string; label: string; total?: number | null; fields: Field[] }

export interface Item {
  id: string
  groupKey: string
  group: string
  title: string
  subtitle: string
  year: number
  n: number | null
  priority: number
  images: ImageRef[]
  sections: Section[]
  overlays: Record<string, Overlay>
}

export interface DatasetMeta {
  name: string
  schema: number
  covariateNote?: string
  years: number[]
  nItems: number
  sources: string[]
}

export interface Dataset { meta: DatasetMeta; items: Item[] }

// ---- adjudication results (stored in IndexedDB) ----
export type Choice = 'claude' | 'codex' | 'current' | 'custom' | 'cant_read' | null

export interface FieldResult {
  choice: Choice
  value: number | null       // resolved numeric value (null for cant_read / blank)
  custom?: string            // raw text the user typed
}

export type ItemStatus = 'untouched' | 'in_progress' | 'done' | 'wrong_page'

export interface ItemResult {
  itemId: string
  fields: Record<string, FieldResult>
  wrongPage?: boolean
  notes?: string
  status: ItemStatus
  updatedAt: number
}
