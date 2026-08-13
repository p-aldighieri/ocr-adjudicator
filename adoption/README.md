# Adoption Adjudicator

**A second, sibling adjudication app in this repo — same machinery as the OCR Adjudicator, different
domain.** Where the parent app confirms *numbers on a scan*, this one establishes source-level
ground truth for textbook-adoption evidence: most importantly, the title words actually printed on
the page. Canonical-book identification and matching method are a separate downstream operation and
are intentionally absent from this app and its exports.

Static React + TS + Tailwind SPA · HashRouter · Dexie/IndexedDB autosave · re-importable JSON export ·
PWA (offline after first load). No backend, no tracking. It lives in `adoption/` and is a **separate
npm project** from the app at the repo root — nothing here imports from `../src`.

**Live app:** <https://p-aldighieri.github.io/ocr-adjudicator/adoption/> (boots with the 3-item
sample). **Current real dataset** (424 source-grounded review items from the 2026-08-07 adoption master, 204 MB):
[`adoption-dataset.zip`](https://github.com/p-aldighieri/ocr-adjudicator/releases/download/adoption-dataset-v4/adoption-dataset.zip)
— download it on any device, then **⚙ Settings → Import dataset .zip**. Everything stays in the
browser's local storage; works on Mac/Windows/Linux browsers, Android Chrome, and iOS 16.4+ Safari.

---

## Run it

```bash
cd adoption
npm install
npm run dev          # http://localhost:5173  (uses adoption/public/dataset/ as the bundled dataset)
```

Other scripts: `npm run build` (`tsc -b && vite build`), `npm run lint`, `npm run preview`.

To rebuild the literal-title review manifest from the newer Aug. 7 selection while reusing only
source/page-compatible assets from the older visual release:

```bash
mkdir -p /tmp/adoption-ground-truth
python3 tools/repair_ground_truth_dataset.py \
  --input dataset-build/dataset.json \
  --old-zip dataset.zip \
  --asset-root dataset-build \
  --overrides tools/ground_truth_overrides.json \
  --output /tmp/adoption-ground-truth/dataset.json \
  --report /tmp/adoption-ground-truth/repair-report.json
python3 tools/validate_ground_truth_dataset.py \
  /tmp/adoption-ground-truth/dataset.json \
  --asset-root dataset-build
```

The normal validator fails on missing assets, disabled placeholders, invalid regions, synthetic
title notation, and downstream matching leakage. It reports missing title-region anchors as warnings;
use `--strict-anchors` only when preparing an artifact in which every title has been spatially audited.

A **hand-written 3-item sample dataset ships in `public/dataset/`**, so `npm run dev` shows a working
app immediately — no builder, no pipeline. The sample exercises all four evidence roles, both
`valueType`s, event-level claims, multi-book bundles, conflicts, and a claim with no candidates at all.
Its page facsimiles are `.svg` placeholders (the real builder emits `.webp`); the app does not care
about the extension.

### The unit of work

One **item = one possible adoption-event bundle**. It carries shared evidence plus extracted title
occurrences. Each occurrence can be accepted exactly, overwritten with the literal page text, or
rejected as “not actually a book title”; reviewers can also add a title the extraction missed.

Three backlogs (`group`), shown as three sections in the Overview:

| group | what's in it |
|---|---|
| `new_records` | events the extractor found that no reviewer has seen |
| `conflicts` | sources or models disagree — read the evidence before choosing |
| `state_laws` | statute-level adoptions: one law, often many books |

---

## Dataset contract

The app loads `dataset.json` plus sibling asset files from one of two places (`src/dataset.ts`):

- **bundled** — fetched from `<base>/dataset/dataset.json` (dev, and any deploy that ships a dataset)
- **opfs** — imported once from a `.zip` into the Origin Private File System (phone, fully offline).
  OPFS wins whenever an imported dataset is present.

The zip may have any nesting; a leading `…dataset/` folder is stripped, and everything else is written
into OPFS preserving sub-directories. Asset paths in `dataset.json` are **relative to the dataset
root** (e.g. `assets/al_1901_minutes.webp`).

> The OPFS folder is named `adoption-dataset` and the IndexedDB database `adoption-adjudicator`, so
> this app can be served from the **same origin** as the OCR Adjudicator without colliding with it.

### `meta`

| field | type | meaning |
|---|---|---|
| `name` | string | dataset identifier; copied into every export |
| `schema` | number | bump when the contract changes |
| `note` | string? | free text about the build, shown nowhere yet |
| `states` | string[] | two-letter codes present |
| `years` | number[] | years present |
| `nItems` | number | sanity check against `items.length` |
| `sources` | string[] | **candidate source names in display order.** Every label and colour in the UI is derived from this list — nothing is hardcoded. Reserved names `custom`, `not_stated`, `cant_tell` must never appear here. |
| `sourceLabels` | Record<string,string>? | pretty names (`{"claude": "Claude"}`); falls back to the raw name |
| `southDefinition` | object? | named/versioned state enumeration used for the `Project South` filter |

### `items[]`

| field | type | meaning |
|---|---|---|
| `id` | string | stable, unique; the key results are stored under |
| `groupKey` | string | **event key** — everything sharing it is the same board action (e.g. `AL\|baldwin\|1901-09-20`) |
| `group` | `new_records` \| `conflicts` \| `state_laws` | which backlog |
| `title` | string | e.g. `"Baldwin County board — 1901-09-20"` |
| `subtitle` | string | state/county line, e.g. `"Baldwin County, Alabama"` |
| `state` | string | two-letter code (queue sorting, search) |
| `year` | number | year of the event |
| `priority` | number | 0..1, higher = review sooner; ≥ 0.7 gets a red ring in the Overview |
| `stateAdoptionRegimeAtEvent` | enum? | `prelaw`, `postlaw`, `ambiguous`, `not_applicable`, or `unknown`; historical status at this event date |
| `stateAdoptionCutoff` | string? | source cutoff retained for auditability |
| `alert` | string? | reviewer instruction shown as an amber banner on the item |
| `note` | string? | builder context shown as a quiet paragraph above the claims |
| `notesPrompt` | string? | placeholder text for the reviewer's notes box |
| `evidence` | EvidenceRef[] | everything the reviewer may look at |
| `eventFields` | ClaimField[]? | claims about the **event itself** (date, unit level, statute citation, term) |
| `books` | BookSection[] | one section per adopted book |

### `EvidenceRef`

| field | type | meaning |
|---|---|---|
| `id` | string | unique **within the item**; `ClaimField.evidenceIds` points at these |
| `role` | `image` \| `pdf_page` \| `text` \| `url` | how it is displayed (below) |
| `file` | string? | relative asset path — required for `image` / `pdf_page` |
| `text` | string? | the snippet itself for `text`; an optional blurb for `url` |
| `href` | string? | external stable URL — required for `url` |
| `label` | string | short chip label, e.g. `"Minutes p. 214"` |
| `sourceLine` | string | citation shown under the evidence: document / page / date |
| `sourceKind` | enum? | explicit `newspaper`, `official_report`, `minutes`, `statute`, `periodical`, or `other` tag |
| `layout` | `prose` \| `table` \| `mixed`? | page layout, orthogonal to source genre |
| `sourceId`, `sourcePath`, `page` | optional | stable build provenance and printed/PDF page identity |
| `regions` | EvidenceRegion[]? | normalized passage, row, column, and cell highlights |

How each role renders (`src/components/EvidencePane.tsx`):

- **`image`** — asset in the zoom-pan viewer (`react-zoom-pan-pinch`), `+ / − / ⤢` controls, label
  badge, `sourceLine` in the footer bar, and optional normalized passage/table highlights.
- **`pdf_page`** — identical viewer. The builder renders the PDF page to an image; the app never
  parses PDFs.
- **`text`** — the snippet verbatim in a scrollable monospace block (wrapping is a Settings toggle),
  with `sourceLine` beneath it.
- **`url`** — a card with the optional blurb and an **Open source ↗** button (new tab,
  `rel="noopener noreferrer"`), the raw URL, and `sourceLine` beneath.

A chip row switches between them when an item has more than one. Chips cited by the currently focused
claim get a sky ring; tapping a claim's **label** jumps the pane to that claim's first evidence, while
tapping a *value* only highlights the claim and leaves the pane where it is.

### `BookSection`

| field | type | meaning |
|---|---|---|
| `key` | string | unique within the item; namespaces this book's result keys |
| `title_as_stated` | string | extractor's proposed literal transcription; it is immutable input, not assumed truth |
| `fields` | ClaimField[] | the claims for this book |
| `note` | string? | builder note about this book |

Publisher, subject, grade span and so on are **claims**, not headers — they are adjudicated, so they
live in `fields`.

### `ClaimField`

| field | type | meaning |
|---|---|---|
| `key` | string | unique within its section |
| `label` | string | shown to the reviewer |
| `valueType` | `choice` \| `text` | `choice` = controlled vocabulary (`options`), narrow custom box; `text` = free transcription, wide custom box |
| `candidates` | Candidate[] | proposals; may be empty (reviewer types it) |
| `default` | string \| null | source name shown as a ghost suggestion; never auto-committed by navigation |
| `agree` | boolean | true when every candidate agrees — drives the `agree` / `conflict` tag |
| `evidenceIds` | string[] | evidence backing this claim |
| `flags` | string[] | builder flags rendered as tags; `weak`, `ocr_low`, `unreliable`, `conflict`, `inferred` get colours, anything else renders grey |
| `options` | string[]? | controlled vocabulary for `choice`, offered as secondary pills |
| `hint` | string? | one-line reviewer instruction under the label |

`Candidate = { source, value: string, note? }`. **All values are strings** — titles, publishers, dates,
`"5"` for a term of years. `source` must be one of `meta.sources`. `note` renders as a caption under
the pill row (useful for "the state report spells the firm out").

---

## What the reviewer produces

Per claim, one `FieldResult`: `{ choice, value, custom? }` where `choice` is a **source name**, or
`custom` (typed / picked from `options`), or `not_stated` (the source is legible and simply doesn't
say), or `cant_tell` (illegible or ambiguous). Those last two are deliberately distinct — they mean
different things downstream.

Each extracted title has a synthetic `title_as_printed` result with three outcomes: use the extraction,
overwrite it, or reject it as a false title. Reviewer-added literal titles live in `addedTitles[]` and
retain the active evidence id when they were created.

Per item, one `ItemResult`: `{ itemId, fields, addedTitles?, insufficient?, notes?, status, updatedAt }`, written to
IndexedDB through a single `mutate()` path in `src/store.tsx` on every keystroke/tap. `insufficient` is
the item-level flag (**⚑ Evidence unavailable / wrong**) for bundles the shipped evidence cannot
settle. It is not used for bad extraction: those rows are corrected/rejected directly.

`status` is derived, never stored by hand (`src/queue.ts`): evidence unavailable → `insufficient`;
no decision → `untouched`; all decisions resolved → `done`; otherwise `in_progress`. The UI calls
these **blocked by evidence**, **new**, **complete**, and **in review**. “Leave in review & Next” never
commits ghost defaults; “Complete & Next” unlocks only when every required decision is explicit.

**Result keys are namespaced**: `"<sectionKey>:<fieldKey>"`, with `_event` as the section key for
`eventFields`. The same `publisher`/`subject` keys repeat for every title extraction in a bundle, so
a flat field key would collide. Use `resultKey()` from `src/queue.ts` — never build the key by hand.

### Export / import

**Settings → Export JSON** writes `adoption-adjudications.json`:

```json
{ "datasetName": "...", "schema": 2, "exportedAt": "...", "nResults": 3,
  "results": { "<itemId>": { "itemId": "...", "fields": { "<section>:<field>": { "choice": "claude", "value": "Ginn & Co." } }, "status": "done", "updatedAt": 0 } } }
```

That file round-trips: **Import adjudications (JSON)** merges it back by `itemId` (survives reinstall,
new device, new phone). It also accepts a bare `{ "<itemId>": {...} }` map.

**Export CSV** starts with one row per extracted or reviewer-added literal title, followed by the
other source claims. `record_origin`, `extracted_value`, and `evidence_id` preserve how a title entered
review. Legacy `book_match` decisions and stale dependent claims under a rejected false-title row are
removed from both CSV and JSON export.

---

## Layout

```
adoption/
  index.html                     app shell (title, theme colour, icons)
  vite.config.ts                 base './' + PWA manifest; shell precached, dataset never is
  package.json                   same stack and versions as the parent app
  tsconfig.{json,app,node}.json  strict TS, project references
  eslint.config.js
  .gitignore                     re-includes public/dataset/ (the root .gitignore excludes it)
  public/
    dataset/dataset.json         SAMPLE dataset (3 items) — source, tracked
    dataset/assets/*.svg         SAMPLE page facsimiles — placeholders for real .webp crops
    pwa-*.png, favicon.png       icons (copied from the parent app)
  src/
    types.ts                     the domain model above (dataset + results)
    dataset.ts                   bundled/OPFS loading, assetURL(), zip import
    db.ts                        Dexie schema: results (one row per item) + meta
    store.tsx                    React context; single mutate() → autosave; settings
    queue.ts                     flatten claims, result keys, status, sorting, progress
    classifications.ts          explicit source/layout, adoption-regime, Project South filters
    exporter.ts                  JSON backup + per-claim CSV + download()
    App.tsx                      HashRouter shell + first-run Welcome
    screens/Overview.tsx         three grouped backlogs with counts and status colours
    screens/Adjudicate.tsx       two-pane: evidence | claims, nav, notes, insufficient flag
    screens/Settings.tsx         queue order, evidence toggle, export/import, danger zone
    components/EvidencePane.tsx  chip row + per-role rendering (generalises the parent's ImageViewer)
    components/ClaimRow.tsx      one claim: candidate pills, options, custom, not-stated, can't-tell
    components/PrintedTitleRow.tsx literal-title accept/overwrite/reject control
  tools/
    repair_ground_truth_dataset.py re-links exact old visual assets + applies reviewed overrides
    validate_ground_truth_dataset.py release gates and structured validation report
    ground_truth_overrides.json versioned source-grounded corrections and highlight boxes
```

---

## Differences from the OCR Adjudicator (and why)

- **Bundles, not cells.** An item carries `books[]` (+ optional `eventFields[]`) instead of
  `sections[]` of numeric fields, and results are keyed `section:field` rather than by a flat field
  key — book-level keys repeat within a bundle.
- **Values are strings.** `Candidate.value`, `FieldResult.value` and the custom box are all text; there
  is no numeric parsing. `N/A` became **Not stated** and `Can't read` became **Can't tell**.
- **Sources are dynamic.** Labels come from `meta.sourceLabels`, dot colours from the position in
  `meta.sources`, and the "✓ All <source>" buttons are generated from the sources actually present in
  the item. The parent's hardcoded `claude`/`codex` maps are gone.
- **Literal title, not matched book.** `book_match`, match method/confidence, authority bridges, and
  canonical identity are stripped at the dataset boundary and from exports. Reviewers can overwrite,
  reject, and add exact printed-title occurrences.
- **Evidence with regions.** `EvidencePane` handles four roles, always shows a citation, and draws
  normalized passage/row/column/cell overlays when the builder supplies them.
- **Wrong page → evidence blocked.** The item-level flag means the shipped evidence cannot settle
  the bundle. Missing or erroneous title extraction is fixed directly and can still become complete.
- **Explicit research focus.** Newspaper and table filters use controlled evidence metadata, not
  guesses from prose. “Ever-adoption state” is explicitly static; `regime active` is historical.
  `Project South v1` names the exact 16-state definition instead of implying Census South.
- **Overview is a grouped list**, not a year matrix: adoption events are sparse and irregular across
  states and years, so a matrix would be mostly empty cells.
- **Isolated storage.** Separate IndexedDB name and OPFS folder, since both apps may be served from
  one GitHub Pages origin.
- **`strict: true`** in `tsconfig.app.json` (the parent omits it). The whole app typechecks clean under
  it with `noUnusedLocals` / `noUnusedParameters` / `erasableSyntaxOnly`.

---

## TODO

- **Upstream builder consolidation** — the committed repair/validator makes the Aug. 7 artifact
  reproducible, but the upstream row-selection/rendering code still needs to become a single
  committed `build_adoption_dataset.py`. It must emit source ids, printed/PDF page identities,
  explicit genre/layout metadata, regions, and a build report; it must refuse page-1 fallbacks.
- **Larger table sample** — the current 424-item v3 manifest exposes only 3 records from Virginia
  Table No. 12, while the verified table contains 112 title cells. The next selection pass must sample
  more table records; a filter alone cannot create that review set.
- **Shells** — the parent has native Windows/macOS wrappers in `tools/`; nothing equivalent exists
  here yet.
- **Keyboard shortcuts** for desktop review (accept-source, next unresolved, flag).
- **Ingest back into the pipeline** — a script that folds the exported CSV/JSON into the canonical
  adoption tables and records who decided what, when.
