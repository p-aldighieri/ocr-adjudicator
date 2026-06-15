#!/usr/bin/env python3
"""
add_column_bands.py — per-field column-band overlays for the dense no-snippet years (1939/47/50).

The ruled tables defeat per-value OCR, but their vertical rules are crisp. We use verified per-field
column positions (normalized x-midpoints — read from the page headers by GPT-5.5/codex, cross-checked
by vision and against known values, e.g. ABC 1939 enrollment 410/522 at cols 10/11), detect each
page's column grid (OpenCV), snap the position to the nearest column, and attach it to that field's
image. Combined with the row band => the cell. Men/women are separate columns.

Run after build_dataset.py:  python tools/add_column_bands.py   (re-zips)
"""
from __future__ import annotations
import json, sys, zipfile
from collections import Counter
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B  # noqa: E402

NOSNIP = (1939, 1947, 1950)
_rules_cache = {}

# verified normalized x-midpoints per (year, field). income/enrollment on the RES page,
# faculty on the GS page (1947/50); all on Table-D-right for 1939.
MANUAL_REP = {
    1939: {"income": 0.1955, "enr_men": 0.5911, "enr_women": 0.6408, "fac_men": 0.8508, "fac_women": 0.8902},
    1947: {"income": 0.3971, "enr_men": 0.2297, "enr_women": 0.2708, "fac_men": 0.5437, "fac_women": 0.5768},
    1950: {"income": 0.5723, "enr_men": 0.2786, "enr_women": 0.3213, "fac_men": 0.5098, "fac_women": 0.5421},
}


def detect_rules(page_path):
    if page_path in _rules_cache:
        return _rules_cache[page_path]
    img = cv2.imread(page_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        _rules_cache[page_path] = []
        return []
    H, W = img.shape
    bw = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, H // 25)))
    vert = cv2.dilate(cv2.erode(bw, vk), vk)
    colsum = vert.sum(axis=0).astype(float)
    rules = []
    if colsum.max() > 0:
        xs = np.where(colsum > 0.35 * colsum.max())[0]
        if len(xs):
            start = prev = xs[0]
            for x in xs[1:]:
                if x - prev > 8:
                    rules.append((start + prev) / 2 / W); start = x
                prev = x
            rules.append((start + prev) / 2 / W)
    _rules_cache[page_path] = rules
    return rules


def col_intervals(rules):
    return list(zip(rules[:-1], rules[1:]))


def col_index(x, cols):
    for i, (a, b) in enumerate(cols):
        if a <= x <= b:
            return i
    return None


def page_for(year, row, field_key):
    g = lambda c: (row.get(c) or "").strip() or None
    if year == 1939:
        return g("resources_image")
    if year in (1947, 1950):
        return g("gs_image") if field_key.startswith("fac") else g("res_image")
    return None


def band_for(rx, cols):
    if not cols:
        return None
    i = min(range(len(cols)), key=lambda k: abs((cols[k][0] + cols[k][1]) / 2 - rx))
    a, b = cols[i]
    return (round(a, 4), round(b - a, 4)) if abs((a + b) / 2 - rx) < 0.04 else None


def main():
    ds_path = B.DEFAULT_OUT / "dataset.json"
    ds = json.loads(ds_path.read_text(encoding="utf-8"))
    for it in ds["items"]:
        for ov in it["overlays"].values():
            ov.pop("cols", None)

    man = {}
    for year in NOSNIP:
        for ror, row in B.load_csv(B.PANELS / f"manifest_{year}.csv").items():
            man[(ror, year)] = row

    n_added = 0
    cov = Counter()
    for it in ds["items"]:
        if it["year"] not in NOSNIP:
            continue
        row = man.get((it["groupKey"], it["year"]))
        if not row:
            continue
        reps = MANUAL_REP.get(it["year"], {})
        for sec in it["sections"]:
            for f in sec["fields"]:
                rx = reps.get(f["key"])
                page = page_for(it["year"], row, f["key"])
                img_id = f.get("imageId")
                if rx is None or not page or not img_id:
                    continue
                band = band_for(rx, col_intervals(detect_rules(page)))
                if not band:
                    continue
                ov = it["overlays"].setdefault(img_id, {"row": None, "boxes": []})
                ov.setdefault("cols", [])
                if not any(c["field"] == f["key"] for c in ov["cols"]):
                    ov["cols"].append({"field": f["key"], "x": band[0], "w": band[1]})
                    n_added += 1; cov[(it["year"], f["key"])] += 1

    ds_path.write_text(json.dumps(ds), encoding="utf-8")
    print(f"added {n_added} column bands")
    for k in sorted(cov):
        print(f"  {k}: {cov[k]}")

    zpath = B.DEFAULT_OUT.parent / "dataset.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        z.write(ds_path, "dataset.json")
        for fp in sorted((B.DEFAULT_OUT / "images").glob("*.webp")):
            z.write(fp, f"images/{fp.name}")
    print(f"re-zipped {zpath} ({zpath.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
