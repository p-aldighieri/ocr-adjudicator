#!/usr/bin/env python3
"""
find_columns_celloc.py — objectively locate the income/faculty/enrollment COLUMN for the dense
no-snippet years by OCR-ing individual grid cells and matching the institution's KNOWN value.

Per-row OCR merges adjacent columns into one token, but a single gridline-bounded CELL is isolated
and OCRs cleanly. For sampled institutions we crop each column's cell on the located row, OCR it, and
see which column reads the known final_income / final_faculty / final_enrollment. The modal column
(+ its normalized x-midpoint) is the answer — verified, not guessed.

Run: python tools/find_columns_celloc.py    (prints MANUAL_REP entries to paste into add_column_bands.py)
"""
from __future__ import annotations
import sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B          # noqa: E402
from add_column_bands import detect_rules, col_intervals  # noqa: E402

_eng = None
_pages = {}

def engine():
    global _eng
    if _eng is None:
        from rapidocr_onnxruntime import RapidOCR
        _eng = RapidOCR(intra_op_num_threads=8)
    return _eng

def page_img(p):
    if p not in _pages:
        _pages[p] = Image.open(p).convert("RGB")
    return _pages[p]

def cell_digits(arr):
    if arr is None or arr.size == 0 or arr.shape[0] < 4 or arr.shape[1] < 4:
        return ""
    try:
        res, _ = engine()(arr)
    except Exception:
        return ""
    best = ""
    for box, txt, score in (res or []):
        d = "".join(c for c in str(txt) if c.isdigit())
        if len(d) > len(best):
            best = d
    return best

COVS = [("income", "res_image", "final_income"),
        ("faculty", "gs_image", "final_faculty"),
        ("enrollment", "res_image", "final_enrollment")]
# 1939 income/enr/fac are all on the resources page:
COVS_1939 = [("income", "resources_image", "final_income"),
             ("faculty", "resources_image", "final_faculty"),
             ("enrollment", "resources_image", "final_enrollment")]

def find(year, max_samples=24):
    man = B.load_csv(B.PANELS / f"manifest_{year}.csv")
    covs = COVS_1939 if year == 1939 else COVS
    out = {}
    for cov, pagecol, valcol in covs:
        votes = Counter(); mids = defaultdict(list); used = 0; hit = 0
        for ror, row in man.items():
            page = (row.get(pagecol) or "").strip()
            n = B.num_or_none(row.get("n") or row.get("inst_number"))
            val = B.num_or_none(row.get(valcol))
            if not page or n is None or val is None:
                continue
            target = B.digits(val)
            if len(target) < 2:
                continue
            loc = B.locate_row(page, n)
            if not loc:
                continue
            yc, pitch, W, H = loc
            rules = detect_rules(page)
            if len(rules) < 3:
                continue
            cols = col_intervals(rules)
            try:
                pil = page_img(page)
            except Exception:
                continue
            y0 = max(0, int(yc - 0.6 * pitch)); y1 = min(H, int(yc + 0.6 * pitch))
            if y1 - y0 < 6:
                continue
            used += 1
            for ci, (a, b) in enumerate(cols):
                x0 = max(0, int(a * W) - 3); x1 = min(W, int(b * W) + 3)
                if x1 - x0 < 6:
                    continue
                if cell_digits(np.array(pil.crop((x0, y0, x1, y1)))) == target:
                    votes[ci] += 1; mids[ci].append((a + b) / 2); hit += 1
                    break
            if used >= max_samples and votes:
                break
        if votes:
            ci, c = votes.most_common(1)[0]
            mid = sorted(mids[ci])[len(mids[ci]) // 2]
            out[cov] = round(mid, 4)
            print(f"  {year} {cov:10}: col idx {ci}  votes {c}/{used}  x-mid {mid:.3f}")
        else:
            print(f"  {year} {cov:10}: NOT FOUND (used {used})")
    return out

def main():
    result = {}
    for year in (1947, 1950, 1939):
        print(f"[{year}]")
        result[year] = find(year)
    print("\nMANUAL_REP = {")
    for y, d in result.items():
        print(f"    {y}: {d},")
    print("}")

if __name__ == "__main__":
    main()
