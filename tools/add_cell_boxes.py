#!/usr/bin/env python3
"""
add_cell_boxes.py — per-value boxes for the dense no-snippet years (1939/47/50).

These ruled tables defeat per-word OCR (and Mistral OCR returns the values but no coordinates), so
the reliable "box around the number" is the GRID CELL: the intersection of the verified column band
and the located row band. On these tables the columns are narrow, so the cell is a tight rectangle
around the value. We add a cell box for any field that has a column band + row band but no OCR box yet.

Run last (after add_column_bands + add_fullpage_overlays):  python tools/add_cell_boxes.py  (re-zips)
"""
from __future__ import annotations
import json, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B  # noqa: E402

NOSNIP = (1939, 1947, 1950)


def main():
    ds_path = B.DEFAULT_OUT / "dataset.json"
    ds = json.loads(ds_path.read_text(encoding="utf-8"))
    n = 0
    for it in ds["items"]:
        if it["year"] not in NOSNIP:
            continue
        for ov in it["overlays"].values():
            row = ov.get("row")
            cols = ov.get("cols") or []
            if not row or not cols:
                continue
            # idempotent: drop prior cell boxes, keep real OCR boxes
            ov["boxes"] = [b for b in ov.get("boxes", []) if b.get("source") != "cell"]
            have = {b["field"] for b in ov["boxes"]}
            for c in cols:
                if c["field"] in have:
                    continue
                ov["boxes"].append({
                    "field": c["field"], "source": "cell",
                    "x": c["x"], "y": round(row["y"], 4),
                    "w": c["w"], "h": round(row["h"], 4),
                })
                n += 1
    ds_path.write_text(json.dumps(ds), encoding="utf-8")
    print(f"added {n} grid cell boxes")

    zpath = B.DEFAULT_OUT.parent / "dataset.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        z.write(ds_path, "dataset.json")
        for fp in sorted((B.DEFAULT_OUT / "images").glob("*.webp")):
            z.write(fp, f"images/{fp.name}")
    print(f"re-zipped {zpath} ({zpath.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
