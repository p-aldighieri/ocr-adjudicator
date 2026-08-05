import JSZip from 'jszip'
import type { Dataset } from './types'
import { getMeta, setMeta } from './db'

// Dataset can come from two places:
//  - 'bundled': fetched from <base>/dataset/ (used in dev / when the site ships a dataset)
//  - 'opfs':    imported once from a .zip into the Origin Private File System (phone, fully offline)
type Source = 'bundled' | 'opfs'

const BASE = import.meta.env.BASE_URL
// distinct OPFS folder: the OCR adjudicator uses 'dataset' and may share this origin
const OPFS_DIR = 'adoption-dataset'
const urlCache = new Map<string, string>()

async function opfsRoot(): Promise<FileSystemDirectoryHandle> {
  return await navigator.storage.getDirectory()
}

async function opfsDatasetDir(create = false): Promise<FileSystemDirectoryHandle | null> {
  try {
    const root = await opfsRoot()
    return await root.getDirectoryHandle(OPFS_DIR, { create })
  } catch {
    return null
  }
}

async function opfsHasDataset(): Promise<boolean> {
  const dir = await opfsDatasetDir(false)
  if (!dir) return false
  try {
    await dir.getFileHandle('dataset.json')
    return true
  } catch {
    return false
  }
}

export async function currentSource(): Promise<Source> {
  if (await opfsHasDataset()) return 'opfs'
  return 'bundled'
}

export async function loadDataset(): Promise<{ data: Dataset; source: Source } | null> {
  const source = await currentSource()
  if (source === 'opfs') {
    const dir = await opfsDatasetDir(false)
    if (!dir) return null
    const fh = await dir.getFileHandle('dataset.json')
    const file = await fh.getFile()
    return { data: JSON.parse(await file.text()) as Dataset, source }
  }
  // bundled
  try {
    const res = await fetch(`${BASE}dataset/dataset.json`, { cache: 'no-cache' })
    if (!res.ok) return null
    return { data: (await res.json()) as Dataset, source: 'bundled' }
  } catch {
    return null
  }
}

/**
 * Resolve an evidence asset path (e.g. "assets/al_1901_minutes.webp") to a usable URL.
 * Unlike the OCR app this keeps arbitrary nesting — evidence assets are grouped by state/year.
 */
export async function assetURL(file: string): Promise<string> {
  const cached = urlCache.get(file)
  if (cached) return cached
  const source = await currentSource()
  if (source === 'opfs') {
    const dir = await opfsDatasetDir(false)
    if (!dir) return ''
    const parts = file.split('/').filter(Boolean)
    let h: FileSystemDirectoryHandle = dir
    for (let i = 0; i < parts.length - 1; i++) h = await h.getDirectoryHandle(parts[i])
    const fh = await h.getFileHandle(parts[parts.length - 1])
    const url = URL.createObjectURL(await fh.getFile())
    urlCache.set(file, url)
    return url
  }
  const url = `${BASE}dataset/${file}`
  urlCache.set(file, url)
  return url
}

async function writeNested(root: FileSystemDirectoryHandle, path: string, data: Blob): Promise<void> {
  const parts = path.split('/').filter(Boolean)
  let h: FileSystemDirectoryHandle = root
  for (let i = 0; i < parts.length - 1; i++) h = await h.getDirectoryHandle(parts[i], { create: true })
  const fh = await h.getFileHandle(parts[parts.length - 1], { create: true })
  const w = await fh.createWritable()
  await w.write(data)
  await w.close()
}

/** Import a dataset .zip (dataset.json + assets/**) into OPFS for offline use. */
export async function importDatasetZip(
  blob: Blob,
  onProgress?: (done: number, total: number, label: string) => void,
): Promise<void> {
  const zip = await JSZip.loadAsync(blob)
  const root = await opfsRoot()
  // wipe any prior dataset
  try { await root.removeEntry(OPFS_DIR, { recursive: true }) } catch { /* none */ }
  const dir = await root.getDirectoryHandle(OPFS_DIR, { create: true })

  const entries = Object.values(zip.files).filter((f) => !f.dir)
  let done = 0
  for (const entry of entries) {
    // tolerate a top folder ("adoption-dataset/assets/x.webp" -> "assets/x.webp")
    const name = entry.name.replace(/^.*?dataset\//, '')
    const leaf = name.split('/').pop() ?? ''
    if (!leaf || leaf.startsWith('.') || name.includes('__MACOSX')) { done++; continue }
    const data = await entry.async('blob')
    await writeNested(dir, name, data)
    done++
    onProgress?.(done, entries.length, entry.name)
  }
  urlCache.clear()
  await setMeta('datasetImportedAt', Date.now())
}

export async function fetchAndImportZip(
  url: string,
  onProgress?: (done: number, total: number, label: string) => void,
): Promise<void> {
  onProgress?.(0, 1, 'downloading…')
  const res = await fetch(url)
  if (!res.ok) throw new Error(`download failed: ${res.status}`)
  const blob = await res.blob()
  await importDatasetZip(blob, onProgress)
}

export async function clearOpfsDataset(): Promise<void> {
  const root = await opfsRoot()
  try { await root.removeEntry(OPFS_DIR, { recursive: true }) } catch { /* none */ }
  urlCache.clear()
}

export async function datasetImportedAt(): Promise<number | null> {
  return await getMeta<number | null>('datasetImportedAt', null)
}
