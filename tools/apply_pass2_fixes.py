#!/usr/bin/env python3
"""
apply_pass2_fixes.py — apply the pass-2 repair spec to dataset.json and emit the
preserved-adjudications JSON (resets only repaired records).

Mirrors tools/apply_pass1_fixes.py but is spec-driven so the splice batches can be
applied incrementally.

Spec (JSON) operations:
  subtitle_state: {ror_suffix: "NewState"}            # replaces text before '·', keeps annotation
  subtitle_note:  {ror_suffix or item_id: "note"}     # replaces/sets the annotation after '·'
  absent: [{item_id, note}]                           # clear candidates + annotate; preserved: auto-N/A done
  unflag: [item_id, ...]                              # preserved: drop wrongPage, keep fields
  keep_note: {item_id: "extra note"}                  # preserved: append note, keep record
  field_set: {item_id: {field: {custom: str}|{value: n, source: str}}}
                                                      # preserved: overwrite single fields (custom)
  reset: [item_id, ...]                               # preserved: DROP record so the RA redoes it
  splice: [{item_id, n, images: [...], candidates: {field: [{source, value}]}, note}]
                                                      # dataset: replace images/n/candidates
Usage:
  python tools/apply_pass2_fixes.py SPEC.json --dataset public/dataset/dataset.json \
      --results ~/Downloads/adjudications_first_pass.json \
      --out-preserved ~/Downloads/adjudications_pass2_preserved.json [--dry-run]
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path


def ror_of(item) -> str:
    return item['groupKey'].rsplit('/', 1)[-1]


def set_subtitle(item, state=None, note=None):
    parts = [p.strip() for p in item['subtitle'].split('·', 1)]
    cur_state = parts[0] if parts else ''
    cur_note = parts[1] if len(parts) > 1 else ''
    new_state = state if state is not None else cur_state
    new_note = note if note is not None else cur_note
    item['subtitle'] = f"{new_state} · {new_note}" if new_note else new_state


def na_field(custom='N/A'):
    return {'choice': 'custom', 'value': None, 'custom': custom}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', type=Path)
    ap.add_argument('--dataset', type=Path, required=True)
    ap.add_argument('--results', type=Path, required=True)
    ap.add_argument('--out-preserved', type=Path, required=True)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    spec = json.loads(args.spec.read_text())
    ds = json.loads(args.dataset.read_text(encoding='utf-8'))
    res_doc = json.loads(Path(args.results).expanduser().read_text())
    results = res_doc.get('results', res_doc)
    items = {it['id']: it for it in ds['items']}
    log = []

    # --- dataset ops -------------------------------------------------------
    for ror, state in (spec.get('subtitle_state') or {}).items():
        hit = 0
        for it in ds['items']:
            if ror_of(it) == ror:
                set_subtitle(it, state=state)
                hit += 1
        log.append(f"subtitle_state {ror} -> {state} ({hit} items)")

    for key, note in (spec.get('subtitle_note') or {}).items():
        hit = 0
        for it in ds['items']:
            if it['id'] == key or ror_of(it) == key:
                set_subtitle(it, note=note)
                hit += 1
        log.append(f"subtitle_note {key} ({hit} items)")

    for a in spec.get('absent') or []:
        it = items[a['item_id']]
        for sec in it['sections']:
            for f in sec['fields']:
                f['candidates'] = []
                f['default'] = None
                f['agree'] = False
        set_subtitle(it, note=a['note'])
        log.append(f"absent {a['item_id']}")

    for sp in spec.get('splice') or []:
        it = items[sp['item_id']]
        if 'n' in sp:
            it['n'] = sp['n']
        if 'images' in sp:
            it['images'] = sp['images']
            it['overlays'] = {}
            # remap field->image references: income prefers the R-side page, others L
            by_side = {im.get('side'): im['id'] for im in sp['images']}
            first = sp['images'][0]['id'] if sp['images'] else None
            for sec in it['sections']:
                for f in sec['fields']:
                    if f['key'] == 'income':
                        f['imageId'] = by_side.get('R', first)
                    else:
                        f['imageId'] = by_side.get('L', first)
        if 'images' in sp or 'candidates' in sp:
            # the old page/row was wrong, so ALL old candidates are junk: clear every
            # field, then install the freshly-read values (if any) for this item
            new_cands = sp.get('candidates') or {}
            for sec in it['sections']:
                for f in sec['fields']:
                    cands = new_cands.get(f['key']) or []
                    f['candidates'] = cands
                    vals = {c['value'] for c in cands}
                    f['agree'] = len(vals) == 1 and len(cands) >= 2
                    f['default'] = cands[0]['source'] if cands and len(vals) == 1 else None
        if sp.get('note'):
            set_subtitle(it, note=sp['note'])
        log.append(f"splice {sp['item_id']} (n={sp.get('n')})")

    # --- preserved results -------------------------------------------------
    preserved = dict(results)
    now = int(time.time() * 1000)

    for a in spec.get('absent') or []:
        iid = a['item_id']
        it = items[iid]
        fields = {f['key']: na_field() for sec in it['sections'] for f in sec['fields']}
        old = preserved.get(iid) or {}
        preserved[iid] = {'itemId': iid, 'fields': fields, 'status': 'done',
                          'notes': a['note'], 'updatedAt': now}
        if old.get('notes') and old['notes'] != a['note']:
            preserved[iid]['notes'] = f"{a['note']} | RA: {old['notes']}"

    for iid in spec.get('unflag') or []:
        r = preserved.get(iid)
        if r:
            r.pop('wrongPage', None)
            r['updatedAt'] = now

    for iid, extra in (spec.get('keep_note') or {}).items():
        r = preserved.get(iid)
        if r is not None:
            r['notes'] = (r.get('notes') + ' | ' if r.get('notes') else '') + extra
            r['updatedAt'] = now

    for iid, fmap in (spec.get('field_set') or {}).items():
        r = preserved.setdefault(iid, {'itemId': iid, 'fields': {}, 'status': 'done', 'updatedAt': now})
        for fk, fv in fmap.items():
            if 'custom' in fv:
                val = fv.get('value')
                r['fields'][fk] = {'choice': 'custom', 'value': val, 'custom': fv['custom']}
            else:
                r['fields'][fk] = {'choice': fv.get('source', 'custom'), 'value': fv['value']}
        r['updatedAt'] = now

    # Reset = TOMBSTONE, not deletion: the app's import merges by itemId (bulkPut),
    # so a dropped record would leave the stale result in the adjudicator's IndexedDB.
    # A blank untouched record overwrites it and clears the wrongPage flag.
    for iid in spec.get('reset') or []:
        preserved[iid] = {'itemId': iid, 'fields': {}, 'status': 'untouched', 'updatedAt': now}

    # normalize stored status snapshots (the app recomputes live, but downstream
    # scripts read the stored field): done = all 5 fields decided, no wrongPage
    n_fields = {it['id']: sum(len(s['fields']) for s in it['sections']) for it in ds['items']}
    for iid, r in preserved.items():
        if r.get('wrongPage'):
            r['status'] = 'wrong_page'
            continue
        decided = sum(1 for fr in (r.get('fields') or {}).values() if fr and fr.get('choice'))
        total = n_fields.get(iid, 5)
        r['status'] = 'done' if decided >= total and total > 0 else ('untouched' if decided == 0 else 'in_progress')

    log.append(f"preserved: {len(preserved)} records "
               f"(input {len(results)}, reset {len(spec.get('reset') or [])}, "
               f"auto-N/A {len(spec.get('absent') or [])})")

    for line in log:
        print(line)
    if args.dry_run:
        print("DRY RUN — nothing written")
        return

    args.dataset.write_text(json.dumps(ds, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    out = {'datasetName': res_doc.get('datasetName', 'unknown'), 'schema': 1,
           'exportedAt': res_doc.get('exportedAt'), 'note': 'pass2-preserved',
           'nResults': len(preserved), 'results': preserved}
    Path(args.out_preserved).expanduser().write_text(json.dumps(out, ensure_ascii=False))
    print(f"wrote {args.dataset} and {args.out_preserved}")


if __name__ == '__main__':
    main()
