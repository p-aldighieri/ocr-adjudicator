#!/usr/bin/env python3
"""
add_fullpage_overlays.py — give the WIDE full pages the same row/column/value overlays as the
snippets, for every year.

Each snippet (and each no-snippet auto-crop) is a pixel-exact, full-width slice of its full page, so
we locate it inside the full page by template matching (no new OCR), then map its row band + value
boxes onto the full page and add full-height column bands snapped to the page's printed gridlines.

Run after build_dataset.py + add_column_bands.py:  python tools/add_fullpage_overlays.py
"""
from __future__ import annotations
import json, sys, zipfile
from collections import defaultdict
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B            # noqa: E402
from add_column_bands import detect_rules, col_intervals  # noqa: E402

IMG = B.DEFAULT_OUT / "images"
_gray = {}
_rules = {}

def gray(file):
    if file not in _gray:
        _gray[file] = cv2.imread(str(IMG / Path(file).name), cv2.IMREAD_GRAYSCALE)
    return _gray[file]

def rules_for(file):
    if file not in _rules:
        _rules[file] = detect_rules(str(IMG / Path(file).name))
    return _rules[file]

def match(snip_file, full_file):
    """Return (top_y_px, snippet_h_px, full_h_px, conf) of the snippet inside the full page."""
    s = gray(snip_file); F = gray(full_file)
    if s is None or F is None or s.shape[0] >= F.shape[0]:
        return None
    if s.shape[1] != F.shape[1]:
        sc = F.shape[1] / s.shape[1]
        s = cv2.resize(s, (F.shape[1], max(1, int(s.shape[0] * sc))))
    if s.shape[0] >= F.shape[0]:
        return None
    res = cv2.matchTemplate(F, s, cv2.TM_CCOEFF_NORMED)
    _, conf, _, loc = cv2.minMaxLoc(res)
    return loc[1], s.shape[0], F.shape[0], conf

def col_band_for_x(full_file, xc):
    rules = rules_for(full_file)
    if len(rules) < 3:
        return None
    cols = col_intervals(rules)
    i = min(range(len(cols)), key=lambda k: abs((cols[k][0] + cols[k][1]) / 2 - xc))
    a, b = cols[i]
    return (round(a, 4), round(b - a, 4)) if (a <= xc <= b or abs((a + b) / 2 - xc) < 0.04) else None

def main():
    ds_path = B.DEFAULT_OUT / "dataset.json"
    ds = json.loads(ds_path.read_text(encoding="utf-8"))
    n_pages = 0
    stats = defaultdict(int)
    for it in ds["items"]:
        _gray.clear()  # bound memory: only this item's pages stay loaded
        fulls = [im for im in it["images"] if im["role"] == "full"]
        snips = [im for im in it["images"] if im["role"] == "snippet"]
        for full in fulls:                       # idempotent: drop prior full-page overlays
            it["overlays"].pop(full["id"], None)
        if not fulls or not snips:
            continue
        for snip in snips:
            ov = it["overlays"].get(snip["id"])
            if not ov:
                continue
            # find the parent full page by best template match
            best = None
            for full in fulls:
                m = match(snip["file"], full["file"])
                if m and (best is None or m[3] > best[1][3]):
                    best = (full, m)
            if not best or best[1][3] < 0.4:
                continue
            full, (top, sh, fh, conf) = best
            def ty(y):  # snippet-normalized y -> full-normalized y
                return round((top + y * sh) / fh, 4)
            fo = it["overlays"].setdefault(full["id"], {"row": None, "boxes": [], "cols": []})
            fo.setdefault("cols", [])
            if ov.get("row") and not fo["row"]:
                fo["row"] = {"y": ty(ov["row"]["y"]), "h": round(ov["row"]["h"] * sh / fh, 4)}
            for b in ov.get("boxes", []):
                fo["boxes"].append({**b, "y": ty(b["y"]), "h": round(b["h"] * sh / fh, 4)})
            # column bands: carry over the crop's own cols, else derive from value-box x
            have = {c["field"] for c in fo["cols"]}
            for c in ov.get("cols", []):
                if c["field"] not in have:
                    fo["cols"].append({"field": c["field"], "x": c["x"], "w": c["w"]}); have.add(c["field"])
            for b in ov.get("boxes", []):
                if b["field"] in have:
                    continue
                band = col_band_for_x(full["file"], b["x"] + b["w"] / 2)
                if band:
                    fo["cols"].append({"field": b["field"], "x": band[0], "w": band[1]}); have.add(b["field"])
            n_pages += 1
            stats[it["year"]] += 1
    ds_path.write_text(json.dumps(ds), encoding="utf-8")
    print(f"added overlays to {n_pages} full pages; by year: {dict(sorted(stats.items()))}")

    zpath = B.DEFAULT_OUT.parent / "dataset.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        z.write(ds_path, "dataset.json")
        for f in sorted(IMG.glob("*.webp")):
            z.write(f, f"images/{f.name}")
    print(f"re-zipped {zpath} ({zpath.stat().st_size/1e6:.1f} MB)")

if __name__ == "__main__":
    main()
