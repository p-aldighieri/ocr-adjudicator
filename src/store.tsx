import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Dataset, Item, ItemResult, FieldResult } from './types'
import { loadDataset } from './dataset'
import { db, getAllResults, getMeta, saveResult, setMeta } from './db'
import { computeStatus, type QueueFilter, type QueueMode } from './queue'

export interface Settings {
  queueMode: QueueMode
  filter: QueueFilter
  showOverlays: boolean
  showRow: boolean
}

const DEFAULT_SETTINGS: Settings = { queueMode: 'year', filter: 'all', showOverlays: true, showRow: true }

interface Store {
  loading: boolean
  hasDataset: boolean
  source: 'bundled' | 'opfs' | null
  dataset: Dataset | null
  items: Item[]
  results: Record<string, ItemResult>
  settings: Settings
  setSettings: (p: Partial<Settings>) => void
  setFieldResult: (itemId: string, fieldKey: string, fr: FieldResult) => void
  setWrongPage: (itemId: string, v: boolean) => void
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

  useEffect(() => { void reload() }, [reload])

  const items = useMemo(() => dataset?.items ?? [], [dataset])

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

  const setWrongPage = useCallback((itemId: string, v: boolean) => {
    mutate(itemId, (r) => { r.wrongPage = v })
  }, [mutate])

  const setNotes = useCallback((itemId: string, notes: string) => {
    mutate(itemId, (r) => { r.notes = notes })
  }, [mutate])

  // Restore adjudications from an exported file (merges by itemId — survives reinstall / new device)
  const importResults = useCallback(async (json: unknown): Promise<number> => {
    const obj = json as { results?: Record<string, ItemResult> }
    const map = (obj?.results ?? json) as Record<string, ItemResult>
    const rows = Object.values(map).filter((r) => r && typeof r === 'object' && 'itemId' in r)
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
    results,
    settings,
    setSettings,
    setFieldResult,
    setWrongPage,
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
