/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { AddedTitleResult, Dataset, Item, ItemResult, FieldResult } from './types'
import { loadDataset } from './dataset'
import { db, getAllResults, getMeta, saveResult, setMeta } from './db'
import { computeStatus, isLegacyTitleField, isMetadataField, type QueueFilter, type QueueMode } from './queue'
import type { ResearchFocus } from './classifications'

export interface Settings {
  queueMode: QueueMode
  filter: QueueFilter
  /**
   * Research focus (newspapers / tables / printed …). Persisted and applied to the review
   * queue itself, so Prev / Next / Complete & Next stay inside the focused set.
   */
  focus: ResearchFocus
  /** soft-wrap long lines in text evidence (off = preserve the source's line breaks) */
  wrapText: boolean
  /** draw normalized passage/table regions supplied by the dataset builder */
  showHighlights: boolean
}

const DEFAULT_SETTINGS: Settings = { queueMode: 'group', filter: 'all', focus: 'all', wrapText: true, showHighlights: true }

interface Store {
  loading: boolean
  hasDataset: boolean
  source: 'bundled' | 'opfs' | null
  dataset: Dataset | null
  items: Item[]
  /** candidate source names in dataset order — every label/colour is derived from this */
  sources: string[]
  sourceLabels: Record<string, string>
  results: Record<string, ItemResult>
  settings: Settings
  setSettings: (p: Partial<Settings>) => void
  setFieldResult: (itemId: string, fieldKey: string, fr: FieldResult) => void
  addTitle: (itemId: string, title: AddedTitleResult) => void
  updateAddedTitle: (itemId: string, titleId: string, value: string) => void
  removeAddedTitle: (itemId: string, titleId: string) => void
  /** value null removes the override — the title falls back to the event-level date */
  setDateOverride: (itemId: string, sectionKey: string, value: string | null) => void
  /** value null removes the override — the verb falls back to the extractor's value */
  setVerbOverride: (itemId: string, sectionKey: string, value: string | null) => void
  setInsufficient: (itemId: string, v: boolean) => void
  setNotes: (itemId: string, notes: string) => void
  importResults: (json: unknown) => Promise<number>
  reload: () => Promise<void>
}

const Ctx = createContext<Store | null>(null)

function blankResult(itemId: string): ItemResult {
  return { itemId, fields: {}, status: 'untouched', updatedAt: Date.now() }
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [source, setSource] = useState<'bundled' | 'opfs' | null>(null)
  const [results, setResults] = useState<Record<string, ItemResult>>({})
  const [settings, setSettingsState] = useState<Settings>(DEFAULT_SETTINGS)

  const reload = useCallback(async () => {
    setLoading(true)
    const loaded = await loadDataset()
    const res = await getAllResults()
    const saved = await getMeta<Settings>('settings', DEFAULT_SETTINGS)
    setDataset(loaded?.data ?? null)
    setSource(loaded?.source ?? null)
    setResults(res)
    setSettingsState({ ...DEFAULT_SETTINGS, ...saved })
    setLoading(false)
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => { void reload() }, 0)
    return () => window.clearTimeout(timer)
  }, [reload])

  const items = useMemo(() => dataset?.items ?? [], [dataset])
  const sources = useMemo(() => dataset?.meta.sources ?? [], [dataset])
  const sourceLabels = useMemo(() => dataset?.meta.sourceLabels ?? {}, [dataset])

  const setSettings = useCallback((p: Partial<Settings>) => {
    setSettingsState((prev) => {
      const next = { ...prev, ...p }
      void setMeta('settings', next)
      return next
    })
  }, [])

  const mutate = useCallback((itemId: string, fn: (r: ItemResult) => void) => {
    setResults((prev) => {
      const cur = prev[itemId] ? { ...prev[itemId], fields: { ...prev[itemId].fields } } : blankResult(itemId)
      fn(cur)
      const item = (dataset?.items ?? []).find((i) => i.id === itemId)
      if (item) cur.status = computeStatus(item, cur)
      cur.updatedAt = Date.now()
      void saveResult(cur)
      return { ...prev, [itemId]: cur }
    })
  }, [dataset])

  const setFieldResult = useCallback((itemId: string, fieldKey: string, fr: FieldResult) => {
    mutate(itemId, (r) => { r.fields[fieldKey] = fr })
  }, [mutate])

  const addTitle = useCallback((itemId: string, title: AddedTitleResult) => {
    mutate(itemId, (r) => { r.addedTitles = [...(r.addedTitles ?? []), title] })
  }, [mutate])

  const updateAddedTitle = useCallback((itemId: string, titleId: string, value: string) => {
    mutate(itemId, (r) => {
      r.addedTitles = (r.addedTitles ?? []).map((title) => title.id === titleId ? { ...title, value } : title)
    })
  }, [mutate])

  const removeAddedTitle = useCallback((itemId: string, titleId: string) => {
    mutate(itemId, (r) => { r.addedTitles = (r.addedTitles ?? []).filter((title) => title.id !== titleId) })
  }, [mutate])

  const setDateOverride = useCallback((itemId: string, sectionKey: string, value: string | null) => {
    mutate(itemId, (r) => {
      const rest = (r.dateOverrides ?? []).filter((o) => o.sectionKey !== sectionKey)
      r.dateOverrides = value === null ? rest : [...rest, { sectionKey, value }]
    })
  }, [mutate])

  const setVerbOverride = useCallback((itemId: string, sectionKey: string, value: string | null) => {
    mutate(itemId, (r) => {
      const rest = (r.verbOverrides ?? []).filter((o) => o.sectionKey !== sectionKey)
      r.verbOverrides = value === null ? rest : [...rest, { sectionKey, value }]
    })
  }, [mutate])

  const setInsufficient = useCallback((itemId: string, v: boolean) => {
    mutate(itemId, (r) => { r.insufficient = v })
  }, [mutate])

  const setNotes = useCallback((itemId: string, notes: string) => {
    mutate(itemId, (r) => { r.notes = notes })
  }, [mutate])

  // Restore adjudications from an exported file (merges by itemId — survives reinstall / new device)
  const importResults = useCallback(async (json: unknown): Promise<number> => {
    const obj = json as { results?: Record<string, ItemResult> }
    const map = (obj?.results ?? json) as Record<string, ItemResult>
    const rows = Object.values(map)
      .filter((r) => r && typeof r === 'object' && 'itemId' in r)
      .map((r) => ({
        ...r,
        fields: Object.fromEntries(Object.entries(r.fields ?? {}).filter(([key]) => {
          const fieldKey = key.slice(key.lastIndexOf(':') + 1)
          return !isLegacyTitleField(fieldKey) && !isMetadataField(fieldKey)
        })),
      }))
    if (rows.length) {
      await db.results.bulkPut(rows.map((r) => ({ ...r, updatedAt: r.updatedAt ?? Date.now() })))
      await reload()
    }
    return rows.length
  }, [reload])

  const value: Store = {
    loading,
    hasDataset: !!dataset,
    source,
    dataset,
    items,
    sources,
    sourceLabels,
    results,
    settings,
    setSettings,
    setFieldResult,
    addTitle,
    updateAddedTitle,
    removeAddedTitle,
    setDateOverride,
    setVerbOverride,
    setInsufficient,
    setNotes,
    importResults,
    reload,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStore(): Store {
  const s = useContext(Ctx)
  if (!s) throw new Error('useStore outside provider')
  return s
}

export { db }
