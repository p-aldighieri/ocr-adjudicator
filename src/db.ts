import Dexie, { type Table } from 'dexie'
import type { ItemResult } from './types'

export interface MetaRow { key: string; value: unknown }

class AppDB extends Dexie {
  results!: Table<ItemResult, string>
  meta!: Table<MetaRow, string>

  constructor() {
    super('ocr-adjudicator')
    this.version(1).stores({
      results: 'itemId, status, updatedAt',
      meta: 'key',
    })
  }
}

export const db = new AppDB()

export async function getMeta<T>(key: string, fallback: T): Promise<T> {
  const row = await db.meta.get(key)
  return row ? (row.value as T) : fallback
}

export async function setMeta(key: string, value: unknown): Promise<void> {
  await db.meta.put({ key, value })
}

export async function saveResult(r: ItemResult): Promise<void> {
  await db.results.put({ ...r, updatedAt: Date.now() })
}

export async function getAllResults(): Promise<Record<string, ItemResult>> {
  const rows = await db.results.toArray()
  const map: Record<string, ItemResult> = {}
  for (const r of rows) map[r.itemId] = r
  return map
}
