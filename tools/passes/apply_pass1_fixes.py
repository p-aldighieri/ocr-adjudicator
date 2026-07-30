#!/usr/bin/env python3
"""Splice verified corrections from the user's first adjudication pass into dataset.json.
Reuses pages already in the bundle (no new images). Run from repo root."""
import json, copy
from pathlib import Path

DS = Path("public/dataset/dataset.json")
ds = json.loads(DS.read_text())
items = {it["id"]: it for it in ds["items"]}

# image descriptor lookup (file -> {id,file,w,h}) from existing items
desc = {}
for it in ds["items"]:
    for im in it["images"]:
        desc.setdefault(im["file"], {k: im[k] for k in ("id", "file", "w", "h")})

def img(file, role, side, label):
    d = dict(desc["images/" + file]); d.update(role=role, side=side, label=label)
    return d

# field_key -> which image side holds it ('inc'=income image, 'enr'=enr/fac image)
def set_values(it, vals, inc_img, enrfac_img):
    for sec in it["sections"]:
        for f in sec["fields"]:
            v = vals.get(f["key"], "KEEPNONE")
            f["imageId"] = (inc_img if f["key"] == "income" else enrfac_img)
            f["flags"] = [fl for fl in f.get("flags", []) if fl in ("weak", "unreliable")]
            if v == "KEEPNONE":
                continue
            if v is None:                    # read in-app: clear candidates, user types
                f["candidates"] = []; f["agree"] = False; f["default"] = None
            else:
                f["candidates"] = [{"source": "current", "value": v}]
                f["agree"] = False; f["default"] = "current"
                if f["key"] == "income":
                    f["confident"] = True
    # refresh section totals
    for sec in it["sections"]:
        nums = [c["value"] for f in sec["fields"] for c in f["candidates"]
                if c.get("source") == "current" and isinstance(c.get("value"), (int, float))]
        if sec["key"] in ("enrollment", "faculty"):
            sec["total"] = sum(nums) if nums else None

# ---- the 10 fixable records: (n, images, income_imgfile, enrfac_imgfile, values) ----
FIX = {
  # Baylor 1939 — Texas page correct; only the auto-crop snippet was wrong. Values: agreeing extractions.
  "005781934_1939": dict(n=3,
    images=[img("802a5ec7676c.webp","full","L","Texas — Names page (Table A)"),
            img("d8bea99e6248.webp","full","R","Texas — Numbers page (Baylor = No. 3)")],
    inc="images/d8bea99e6248.webp", enr="images/d8bea99e6248.webp",
    vals=dict(income=819, enr_men=1693, enr_women=1390, fac_men=94, fac_women=51)),
  # Arizona State — was showing University of Arizona (Tucson). Correct = Arizona State, Tempe.
  "03efmqc40_1953": dict(n=3,
    images=[img("52ca1740d658.webp","full","F","Alabama–Arizona page — Arizona State, Tempe (No. 3)")],
    inc="images/52ca1740d658.webp", enr="images/52ca1740d658.webp",
    vals=dict(income=2125, enr_men=3223, enr_women=1443, fac_men=145, fac_women=54)),
  "03efmqc40_1956": dict(n=4,
    images=[img("f5015c7ae643.webp","full","Lf","Arizona — enrollment & faculty (Arizona State, Tempe = No. 4)"),
            img("8459574733f2.webp","full","Rf","Arizona — income")],
    inc="images/8459574733f2.webp", enr="images/f5015c7ae643.webp",
    vals=dict(income=3554, enr_men=3371, enr_women=1887, fac_men=167, fac_women=58)),
  "03efmqc40_1959": dict(n=5,
    images=[img("3ea9512a1fcd.webp","full","Lf","Arizona — enrollment & faculty (Arizona State, Tempe = No. 5)"),
            img("76e8dd2bb638.webp","full","Rf","Arizona — income")],
    inc="images/76e8dd2bb638.webp", enr="images/3ea9512a1fcd.webp",
    vals=dict(income=3663, enr_men=5199, enr_women=3466, fac_men=354, fac_women=87)),
  # Auburn — listed as "Alabama Polytechnic Inst." pre-1960.
  "02v80fc35_1953": dict(n=5,
    images=[img("52ca1740d658.webp","full","F","Alabama–Arizona page — Ala. Polytechnic / Auburn (No. 5)")],
    inc="images/52ca1740d658.webp", enr="images/52ca1740d658.webp",
    vals=dict(income=6351, enr_men=7671, enr_women=2584, fac_men=433, fac_women=37)),
  "02v80fc35_1962": dict(n=8,
    images=[img("4f4e8bdb1b00.webp","full","Lf","Alabama — enrollment & faculty (Auburn University = No. 8)"),
            img("0c8223e913e5.webp","full","Rf","Alabama — income")],
    inc="images/0c8223e913e5.webp", enr="images/4f4e8bdb1b00.webp",
    vals=dict(income=None, enr_men=None, enr_women=None, fac_men=None, fac_women=None)),
  # Boston College — was showing a State College. Correct = Boston College, Chestnut Hill, No. 12.
  "02n2fzt79_1962": dict(n=12,
    images=[img("2ef8a050af54.webp","full","Lf","Massachusetts — enrollment & faculty (Boston College = No. 12)"),
            img("7b41ecbe6681.webp","full","Rf","Massachusetts — income")],
    inc="images/7b41ecbe6681.webp", enr="images/2ef8a050af54.webp",
    vals=dict(income=None, enr_men=5855, enr_women=2326, fac_men=509, fac_women=80)),
  # Arizona State / Auburn 1947-50 — present in the BB but extraction skipped them.
  # Correct GS (faculty) + RES (income/enrollment) pages are bundled under Univ of Arizona/Alabama.
  "03efmqc40_1947": dict(n=None,
    images=[img("69c2b019144d.webp","full","R","Arizona RES — income/enrollment (Arizona State, Tempe)"),
            img("fdcc9792a57d.webp","full","L","Arizona GS — faculty")],
    inc="images/69c2b019144d.webp", enr="images/69c2b019144d.webp",
    vals=dict(income=None, enr_men=None, enr_women=None, fac_men=None, fac_women=None)),
  "03efmqc40_1950": dict(n=None,
    images=[img("8453bc0b495a.webp","full","R","Arizona RES — income/enrollment (Arizona State, Tempe)"),
            img("2a38bd397809.webp","full","L","Arizona GS — faculty")],
    inc="images/8453bc0b495a.webp", enr="images/8453bc0b495a.webp",
    vals=dict(income=None, enr_men=None, enr_women=None, fac_men=None, fac_women=None)),
  "02v80fc35_1947": dict(n=2,
    images=[img("69c2b019144d.webp","full","R","Alabama RES — income/enrollment (Ala. Polytechnic / Auburn = No. 2)"),
            img("fdcc9792a57d.webp","full","L","Alabama GS — faculty")],
    inc="images/69c2b019144d.webp", enr="images/69c2b019144d.webp",
    vals=dict(income=None, enr_men=None, enr_women=None, fac_men=None, fac_women=None)),
}

for iid, spec in FIX.items():
    it = items[iid]
    it["n"] = spec["n"]
    it["images"] = spec["images"]
    it["overlays"] = {}
    set_values(it, spec["vals"], spec["inc"], spec["enr"])

# ---- N/A records: not separately listed in the Blue Book ----
def mark_na(it, note):
    if note not in it["subtitle"]:
        it["subtitle"] = (it["subtitle"] + " · " + note).strip(" ·")
    for sec in it["sections"]:
        for f in sec["fields"]:
            f["candidates"] = []; f["agree"] = False; f["default"] = None
        if sec["key"] in ("enrollment", "faculty"):
            sec["total"] = None

absent = ["02v80fc35_1939", "03efmqc40_1939"]
for iid in absent:
    mark_na(items[iid], "not in the 1939 Blue Book")
baruch = [i for i in items if i.startswith("023qavy03_")]
for iid in baruch:
    mark_na(items[iid], "part of CCNY (not separately listed pre-1968)")

DS.write_text(json.dumps(ds))
print("fixed records:", len(FIX))
print("N/A absent:", absent, "| Baruch N/A:", len(baruch))
# sanity: report each fixed record's new n + pre-filled income
for iid in FIX:
    it = items[iid]
    inc = next((c["value"] for s in it["sections"] for f in s["fields"] if f["key"]=="income"
                for c in f["candidates"]), None)
    print(f"  {iid}  n={it['n']}  income={inc}  images={[i['file'].split('/')[-1] for i in it['images']]}")
