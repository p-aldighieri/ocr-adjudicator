#!/usr/bin/env python3
"""
add_column_bands.py — add column-band overlays for the dense no-snippet years (1939/47/50).

The ruled tables defeat per-value OCR, but their vertical rules are crisp. For each source page we
detect the column grid (OpenCV), then decide which grid-column is income / enrollment / faculty by a
PER-PAGE VOTE over the value-boxes we did manage to OCR across all institutions on that page (robust:
one stray match can't move the column; a column needs >=2 agreeing votes). The winning column's
x-range is written as a `cols` band onto every item on that page — so even rows whose digits never
OCR'd get the right column highlighted. Combined with the existing row band => the cell.

Run after build_dataset.py:  python tools/add_column_bands.py   (then re-zip if needed)
"""
from __future__ import annotations
import json, csv, sys
from collections import Counter, defaultdict
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B  # noqa: E402

NOSNIP = (1939, 1947, 1950)
_rules_cache = {}


def detect_rules(page_path):
    """Return sorted normalized x-positions of vertical rules on the page, or []."""
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


def page_for(year, row, cov):
    g = lambda c: (row.get(c) or "").strip() or None
    if year == 1939:
        return g("resources_image")
    if year in (1947, 1950):
        return g("gs_image") if cov == "faculty" else g("res_image")
    return None


def main():
    ds_path = B.DEFAULT_OUT / "dataset.json"
    ds = json.loads(ds_path.read_text(encoding="utf-8"))
    items = {it["id"]: it for it in ds["items"]}
    # idempotent: drop any column bands from a previous run
    for it in ds["items"]:
        for ov in it["overlays"].values():
            ov.pop("cols", None)

    # ror/year -> manifest row (for page paths)
    man = {}
    for year in NOSNIP:
        for ror, row in B.load_csv(B.PANELS / f"manifest_{year}.csv").items():
            man[(ror, year)] = row

    # The table layout is IDENTICAL across all pages of a year, so aggregate value-box x-centers
    # across the WHOLE YEAR (hundreds of votes for income) and take one robust column position per
    # covariate; then snap it to each page's own detected rules. Per-page voting is too sparse/noisy.
    year_cov_x = defaultdict(lambda: defaultdict(list))   # year -> cov -> [xcenter,...]
    item_page = defaultdict(dict)                         # item_id -> cov -> page
    for it in ds["items"]:
        if it["year"] not in NOSNIP:
            continue
        row = man.get((it["groupKey"], it["year"]))
        if not row:
            continue
        for sec in it["sections"]:
            cov = sec["key"]
            page = page_for(it["year"], row, cov)
            if not page:
                continue
            item_page[it["id"]][cov] = page
            rules = detect_rules(page)
            if len(rules) < 3:
                continue
            cols = col_intervals(rules)
            for ov in it["overlays"].values():
                for b in ov.get("boxes", []):
                    fcov = "income" if b["field"] == "income" else ("enrollment" if b["field"].startswith("enr") else "faculty")
                    if fcov != cov:
                        continue
                    ci = col_index(b["x"] + b["w"] / 2, cols)
                    if ci is not None:               # record the COLUMN MIDPOINT, not the raw box x
                        year_cov_x[it["year"]][cov].append((cols[ci][0] + cols[ci][1]) / 2)

    def cluster_x(xs):
        """Densest 0.02-wide cluster centre of column-midpoints, or None."""
        if len(xs) < 3:
            return None
        bins = defaultdict(list)
        for x in xs:
            bins[round(x / 0.02)].append(x)
        best = max(bins.values(), key=len)
        if len(best) < max(3, 0.2 * len(xs)):
            return None
        return sum(best) / len(best)

    # Verified column positions (normalized x-midpoint) for the years with no usable OCR anchors.
    # Read from the page headers by GPT-5.5 (codex, xhigh) and cross-checked by vision + the data:
    #   1947/1950 income = 2nd RESOURCES column (after endowment); enrollment = LIVING-QUARTERS men;
    #   faculty = the FACULTY 'M' column on the GS page. Snapped to each page's own rules at apply time.
    MANUAL_REP = {
        1947: {"income": 0.3971, "enrollment": 0.2297, "faculty": 0.5437},
        1950: {"income": 0.5723, "enrollment": 0.2786, "faculty": 0.5098},
    }

    rep = {}   # year -> cov -> representative column-midpoint x (or None)
    for year in NOSNIP:
        inc = cluster_x(year_cov_x[year]["income"])
        enr = cluster_x(year_cov_x[year]["enrollment"])
        fac = cluster_x(year_cov_x[year]["faculty"])
        if inc is not None:                         # income/enrollment share the page -> enforce order
            if enr is not None and enr <= inc:
                enr = None
            if year == 1939 and fac is not None and fac <= inc:  # faculty same page only in 1939
                fac = None
        rep[year] = {"income": inc, "enrollment": enr, "faculty": fac}
        got = ", ".join(f"{k}={v:.3f}" for k, v in rep[year].items() if v is not None)
        print(f"  {year} anchored column-midpoints: {got or '(none)'}")

    # fill years/covariates lacking an OCR anchor with the vision-verified positions
    for year, covs in MANUAL_REP.items():
        for cov, x in covs.items():
            if rep.get(year, {}).get(cov) is None:
                rep.setdefault(year, {})[cov] = x
                print(f"  {year} {cov}: using vision-verified x={x}")

    def band_for(year, cov, cols):
        """Return (a,b) column interval for cov on a page with `cols`, via anchor or schema."""
        rx = rep[year].get(cov)
        if rx is not None:
            i = min(range(len(cols)), key=lambda k: abs((cols[k][0] + cols[k][1]) / 2 - rx))
            if abs((cols[i][0] + cols[i][1]) / 2 - rx) < 0.03:
                return cols[i]
        return None

    n_added = 0
    cov_counts = Counter()
    for it in ds["items"]:
        if it["year"] not in NOSNIP:
            continue
        for sec in it["sections"]:
            cov = sec["key"]
            page = item_page.get(it["id"], {}).get(cov)
            if not page:
                continue
            rules = detect_rules(page)
            if len(rules) < 3:
                continue
            band = band_for(it["year"], cov, col_intervals(rules))
            if not band:
                continue
            a, b = band
            img_id = sec["fields"][0].get("imageId")
            if not img_id:
                continue
            ov = it["overlays"].setdefault(img_id, {"row": None, "boxes": []})
            ov.setdefault("cols", [])
            if not any(c.get("field") == cov for c in ov["cols"]):
                ov["cols"].append({"field": cov, "x": round(a, 4), "w": round(b - a, 4)})
                n_added += 1; cov_counts[cov] += 1

    ds_path.write_text(json.dumps(ds), encoding="utf-8")
    print(f"added {n_added} column bands: {dict(cov_counts)}")

    # re-zip so the phone bundle reflects the updated dataset.json
    import zipfile
    zpath = B.DEFAULT_OUT.parent / "dataset.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        z.write(ds_path, "dataset.json")
        for f in sorted((B.DEFAULT_OUT / "images").glob("*.webp")):
            z.write(f, f"images/{f.name}")
    print(f"re-zipped {zpath} ({zpath.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
