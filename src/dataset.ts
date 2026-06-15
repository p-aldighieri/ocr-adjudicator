import JSZip from 'jszip'
import type { Dataset } from './types'
import { getMeta, setMeta } from './db'

// Dataset can come from two places:
//  - 'bundled': fetched from <base>/dataset/ (used in dev / when the site ships a dataset)
//  - 'opfs':    imported once from a .zip into the Origin Private File System (phone, fully offline)
type Source = 'bundled' | 'opfs'

const BASE = import.meta.env.BASE_URL
const urlCache = new Map<string, string>()

async function opfsRoot(): Promise<FileSystemDirectoryHandle> {
  return await navigator.storage.getDirectory()
}

async function opfsDatasetDir(create = false): Promise<FileSystemDirectoryHandle | null> {
  try {
    const root = await opfsRoot()
    return await root.getDirectoryHandle('dataset', { create })
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
    const fh = await dir!.getFileHandle('dataset.json')
    const file = await fh.getFile()
    return { data: JSON.parse(await file.text()), source }
  }
  // bundled
  try {
    const res = await fetch(`${BASE}dataset/dataset.json`, { cache: 'no-cache' })
    if (!res.ok) return null
    return { data: await res.json(), source: 'bundled' }
  } catch {
    return null
  }
}

/** Resolve an image file path (e.g. "images/abc.webp") to a usable URL. */
export async function imageURL(file: string): Promise<string> {
  if (urlCache.has(file)) return urlCache.get(file)!
  const source = await currentSource()
  if (source === 'opfs') {
    const dir = await opfsDatasetDir(false)
    const parts = file.split('/') // images/abc.webp
    let h: FileSystemDirectoryHandle = dir!
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

/** Import a dataset .zip (dataset.json + images/*) into OPFS for offline use. */
export async function importDatasetZip(
  blob: Blob,
  onProgress?: (done: number, total: number, label: string) => void,
): Promise<void> {
  const zip = await JSZip.loadAsync(blob)
  const root = await opfsRoot()
  // wipe any prior dataset
  try { await root.removeEntry('dataset', { recursive: true }) } catch { /* none */ }
  const dir = await root.getDirectoryHandle('dataset', { create: true })
  const images = await dir.getDirectoryHandle('images', { create: true })

  const entries = Object.values(zip.files).filter((f) => !f.dir)
  let done = 0
  for (const entry of entries) {
    const data = await entry.async('blob')
    const name = entry.name.replace(/^.*?dataset\//, '') // tolerate a top folder
    if (name === 'dataset.json' || name.endsWith('dataset.json')) {
      const fh = await dir.getFileHandle('dataset.json', { create: true })
      const w = await fh.createWritable(); await w.write(data); await w.close()
    } else if (name.startsWith('images/')) {
      const fn = name.slice('images/'.length)
      const fh = await images.getFileHandle(fn, { create: true })
      const w = await fh.createWritable(); await w.write(data); await w.close()
    }
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
  try { await root.removeEntry('dataset', { recursive: true }) } catch { /* none */ }
  urlCache.clear()
}

export async function datasetImportedAt(): Promise<number | null> {
  return await getMeta<number | null>('datasetImportedAt', null)
}
