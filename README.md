# OCR Adjudicator

A mobile-first, **fully-offline** web app for verifying OCR / model extractions against the source
scans they came from — one tap to accept, conflicts surfaced first, work exported as clean data.

It is **general-purpose**: you feed it a *dataset bundle* (a `dataset.json` + recompressed images) and
it lets you adjudicate any set of extracted values cell-by-cell. The first dataset it was built for is
the **College Blue Books** (184 US universities × 8 years, 1939–1965; income / enrollment / faculty),
with two independent extractions (Claude & Codex) to choose between.

<p align="center"><img src="public/pwa-512.png" width="120" alt="icon"></p>

## Why it exists

You have model/OCR guesses and the page images. You want a human to confirm the truth, fast, on a
phone, without a network — and get the result back as data. This app:

- shows the **source scan** big, with **pinch-zoom/pan** and an **overlay** that boxes the value
  Claude/Codex read, highlights the institution's **row**, and (where detectable) its **column**;
- offers a **multiple choice** per cell — Claude's value / Codex's value / **type your own** — plus
  **"Can't read"** and a card-level **"Wrong page / not here"**;
- **pre-selects** the value when the two extractors agree, so confident cells are a single tap;
- orders the queue **by institution** (all years together) or by **priority** (conflicts & low-confidence first);
- saves every choice **instantly to on-device storage** (survives reload/airplane mode);
- **exports** your adjudications as JSON/CSV to merge back on your computer.

## Architecture

```
tools/build_dataset.py   (Python)  manifests + scans  ->  dataset.json + images/*.webp  (+ dataset.zip)
        │                                   the bundle is DATA, kept out of git
        v
src/  (React + TypeScript + Tailwind, Vite, PWA)
        loads the bundle, stores results in IndexedDB, runs 100% client-side / offline
        v
tools/apply_results.py   (Python)  exported results.json  ->  adjudicated_* columns + reconciliation.csv
```

- **No backend.** Everything runs in the browser. After the first load the service worker + the
  imported dataset (in OPFS) make it work with no network.
- **Install on a phone** by opening the deployed URL and tapping *Add to Home screen* (PWA).

## Quick start (development)

```bash
npm install
# build a small sample dataset into public/dataset (served by the dev server):
python tools/build_dataset.py --years 1962 1939 --limit 8
npm run dev            # open http://localhost:5173  (use a narrow / phone-sized window)
```

Build the **full** Blue Book dataset (all 184x8, ~300 MB of WebP, OCR overlays, +zip for phone import):

```bash
python tools/prewarm_ocr.py --of 10 --threads 2   # parallel OCR + encode (~2-3 h, one-time; cached)
python tools/build_dataset.py --zip               # assemble dataset.json + images + dataset.zip (~3 min)
python tools/add_column_bands.py                  # column-band overlays for the dense years; re-zips
```

All steps are incremental: already-encoded images and cached OCR (`tools/.ocr_cache.json`) are reused.
`prewarm_ocr.py` uses staggered subprocesses on purpose — `multiprocessing.Pool` + onnxruntime deadlocks
on Windows. Overlays: snippet years (1953/56/59/62/65) get per-value boxes + a row band; the no-snippet
years (1939/47/50) get a readable auto-cropped row strip with the row highlighted, plus column bands
where they can be located (1939 has enough OCR anchors; 1947/50 keep the row highlight).

## Getting it on your phone

1. `npm run build` and deploy `dist/` (e.g. GitHub Pages — see `.github/workflows/deploy.yml`).
2. On the phone, open the URL -> **Add to Home screen**.
3. First run: **Settings -> Import dataset .zip** (point at `dataset.zip`, served from your PC over wifi
   or downloaded once). It unpacks into the phone's private storage; after that it's fully offline.

## Dataset format (use it for your own OCR task)

`dataset.json`:

```jsonc
{
  "meta": { "name": "...", "schema": 1, "years": [], "sources": ["claude","codex","current"] },
  "items": [{
    "id": "uniqueid",
    "group": "northwestern university",      // items are grouped/ordered by this
    "groupKey": "ror-or-any-stable-key",
    "title": "Northwestern University", "subtitle": "Illinois",
    "year": 1962, "n": 92, "priority": 0.0,  // priority 0..1 -> queue order & "needs attention" ring
    "images": [{ "id":"", "file":"images/x.webp", "w":0, "h":0, "role":"snippet|full", "side":"", "label":"" }],
    "sections": [{
      "key": "income", "label": "Income ($ thousands)", "total": null,
      "fields": [{
        "key": "income", "label": "Income", "imageId": "<image id this value sits on>",
        "candidates": [{ "source":"claude","value":33000 }, { "source":"codex","value":33000 },
                       { "source":"landgrant","value":31000,"ref":true }],
        "agree": true, "default": "claude", "flags": [], "confident": true
      }]
    }],
    "overlays": { "<imageId>": { "row": {"y":0.49,"h":0.10},
                                  "boxes": [{ "field":"income","source":"claude","x":0,"y":0,"w":0,"h":0 }] } }
  }]
}
```

Images referenced by `file` live next to `dataset.json` (e.g. `images/abc.webp`). Coordinates in
`overlays` are normalized 0..1 to the image's original `w`/`h`, so they zoom/pan locked to the scan.

To adapt to a new corpus, write a builder that emits this shape; the app needs no changes.

## Exports

- **Settings -> Export JSON** — `adjudications.json` (full result map; re-importable).
- **Settings -> Export CSV** — one row per field with the chosen value + provenance.
- On the PC: `python tools/apply_results.py adjudications.json` writes the confirmed values into the
  Blue Book manifests' `adjudicated_*` columns and emits a `reconciliation.csv` of changes.

## License

MIT — see [LICENSE](LICENSE).
