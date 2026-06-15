#!/usr/bin/env python3
"""
apply_results.py — take the app's exported adjudications and turn them back into data.

Inputs:
  adjudications.json      (Settings -> Export JSON in the app)
  dataset.json            (the bundle the app used; default ../public/dataset/dataset.json)

Outputs (written next to adjudications.json):
  adjudications_long.csv  one row per adjudicated field: ror_id, year, section, field, choice, value, ...
  adjudications_wide.csv  one row per (ror_id, year): adj_income / adj_enrollment / adj_faculty (+ status)

Optional, with --panels <covariate_panels dir>:
  reconciliation.csv      adj totals vs the panels' current final_*, with a `changed` flag
  (and writes confirmed values into each manifest_{year}.csv adjudicated_* columns where they exist)

Usage:
  python apply_results.py adjudications.json
  python apply_results.py adjudications.json --dataset ../public/dataset/dataset.json \
                          --panels "C:/.../covariate_panels"
"""
from __future__ import annotations
import argparse, csv, json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def chosen(field_result):
    """Return (choice, value) honoring 'can't read' (blank) and missing results."""
    if not field_result:
        return ("", None)
    ch = field_result.get("choice") or ""
    if ch == "cant_read":
        return ("cant_read", None)
    return (ch, num(field_result.get("value")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("--dataset", type=Path, default=HERE.parent / "public" / "dataset" / "dataset.json")
    ap.add_argument("--panels", type=Path, default=None)
    args = ap.parse_args()

    out_dir = args.results.parent
    res_doc = json.loads(args.results.read_text(encoding="utf-8"))
    results = res_doc.get("results", res_doc)  # tolerate raw map
    ds = json.loads(args.dataset.read_text(encoding="utf-8"))
    items = {it["id"]: it for it in ds["items"]}

    long_rows = []
    wide = {}  # (ror, year) -> dict

    for item_id, it in items.items():
        r = results.get(item_id)
        if not r:
            continue
        ror, year = it["groupKey"], it["year"]
        status = r.get("status", "")
        wrong = bool(r.get("wrongPage"))
        notes = r.get("notes", "") or ""
        w = wide.setdefault((ror, year), {
            "ror_id": ror, "university": it.get("title", ""), "year": year,
            "status": status, "wrong_page": "TRUE" if wrong else "",
            "adj_income": None, "adj_enrollment": None, "adj_faculty": None, "notes": notes,
        })
        parts = {"enrollment": [], "faculty": []}
        for sec in it["sections"]:
            for f in sec["fields"]:
                ch, val = chosen(r.get("fields", {}).get(f["key"]))
                if not ch and not wrong:
                    continue
                long_rows.append({
                    "ror_id": ror, "university": it.get("title", ""), "year": year,
                    "section": sec["key"], "field": f["key"], "choice": ch,
                    "value": "" if val is None else val,
                    "status": status, "wrong_page": "TRUE" if wrong else "", "notes": notes,
                })
                if val is None:
                    continue
                if f["key"] == "income":
                    w["adj_income"] = val
                elif sec["key"] == "enrollment":
                    parts["enrollment"].append(val)
                elif sec["key"] == "faculty":
                    parts["faculty"].append(val)
        if parts["enrollment"]:
            w["adj_enrollment"] = sum(parts["enrollment"])
        if parts["faculty"]:
            w["adj_faculty"] = sum(parts["faculty"])

    # write long
    long_path = out_dir / "adjudications_long.csv"
    with open(long_path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["ror_id", "university", "year", "section", "field",
                                            "choice", "value", "status", "wrong_page", "notes"])
        wr.writeheader(); wr.writerows(long_rows)

    # write wide
    wide_path = out_dir / "adjudications_wide.csv"
    with open(wide_path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["ror_id", "university", "year", "adj_income",
                                            "adj_enrollment", "adj_faculty", "status", "wrong_page", "notes"])
        wr.writeheader()
        for w in sorted(wide.values(), key=lambda d: (d["university"], d["year"])):
            wr.writerow({k: ("" if w.get(k) is None else w.get(k)) for k in wr.fieldnames})

    print(f"wrote {long_path}  ({len(long_rows)} field rows)")
    print(f"wrote {wide_path}  ({len(wide)} institution-years)")

    if args.panels:
        reconcile(args.panels, wide, out_dir)


def reconcile(panels: Path, wide: dict, out_dir: Path):
    rows = []
    finals = {}
    for year in (1939, 1947, 1950, 1953, 1956, 1959, 1962, 1965):
        mf = panels / f"manifest_{year}.csv"
        if not mf.exists():
            continue
        with open(mf, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                finals[(row["ror_id"], year)] = row
    for (ror, year), w in wide.items():
        f = finals.get((ror, year), {})
        for cov, key in (("income", "final_income"), ("enrollment", "final_enrollment"), ("faculty", "final_faculty")):
            adj = w.get(f"adj_{cov}")
            cur = num(f.get(key))
            if adj is None and cur is None:
                continue
            rows.append({"ror_id": ror, "year": year, "covariate": cov,
                         "current_final": "" if cur is None else cur,
                         "adjudicated": "" if adj is None else adj,
                         "changed": "TRUE" if (adj is not None and adj != cur) else ""})
    rp = out_dir / "reconciliation.csv"
    with open(rp, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["ror_id", "year", "covariate", "current_final", "adjudicated", "changed"])
        wr.writeheader(); wr.writerows(rows)
    changed = sum(1 for r in rows if r["changed"])
    print(f"wrote {rp}  ({len(rows)} cells, {changed} changed vs current final)")


if __name__ == "__main__":
    main()
