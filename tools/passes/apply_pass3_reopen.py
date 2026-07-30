#!/usr/bin/env python3
"""Pass-3 reopen round: rebuild dataset + preserved JSON so the RA re-adjudicates
(a) every cell tied to his comments / the flagged-cell audit,
(b) the 7 disputed "not printed" income cells + Stanford 1947 (blind, with alert),
(c) the 44 joint-faculty conversions (new convention: total under Men + note),
while keeping all other work preserved. Also reverts the 10 income corrections to
as-printed digits (units handled downstream via income_units_flags.csv).

Inputs:  base dataset (pass-2 shipped)  = /Applications app copy
         preserved v2                   = ~/Downloads/adjudications_pass2_preserved_v2.json
Outputs: <repo>/public/dataset/dataset.json  (+ scratch copy)
         ~/Downloads/adjudications_pass3_preserved.json
         <scratch>/income_units_flags.csv
Run from repo root.
"""
import json, csv, copy, sys
from pathlib import Path

BASE_DS = "/Applications/OCR Adjudicator.app/Contents/Resources/site/dataset/dataset.json"
V2 = "/Users/p-aldighieri/Downloads/adjudications_pass2_preserved_v2.json"
V3 = "/Users/p-aldighieri/Downloads/adjudications_pass3_preserved.json"
SCRATCH = "/private/tmp/claude-501/-Users-p-aldighieri-Library-CloudStorage-OneDrive-Personal-Codebook-ocr-adjudicator/62c5429c-f129-4c56-bd68-ba33958469c8/scratchpad"
REPO_DS = Path("public/dataset/dataset.json")

# ---------------------------------------------------------------- specs
ALERT_INCOME_BLIND = (
    "RE-CHECK INCOME (disputed cell). Find the RESOURCES columns "
    "(Endow't | Total Annual Income | Plant | Volumes in Library) and type EXACTLY the printed "
    "digits of Total Annual Income — even if the number looks tiny (some universities filed in "
    "$ millions; do NOT convert). Only if the cell is truly blank: N/A + note."
)
BLIND = {  # item -> (fields to clear, extra alert text)
    "02y3ad647_1939": (["income"], ""),
    "02y3ad647_1947": (["income"], ""),
    "02y3ad647_1956": (["income"], ""),
    "017zqws13_1962": (["income"], " Beware: a trailing ¶ footnote mark after the number is NOT a digit."),
    "02teq1165_1956": (["income"], ""),
    "043mer456_1965": (["income"], ""),
    "04a5szx83_1965": (["income"], ""),
    "00f54p054_1947": (["income"], " Two prior reads disagreed — carefully identify the Income column (not Endowment)."),
}

# item -> {field: prefill value or None (no candidate, e.g. expect N/A)}, alert
CONFIRM = {
    "00wek6x04_1962": ({"enr_women": 435},
        "Re-read Women enrollment: use the CAMPUS row ('Mayaguez Campus', 4a), NOT the '-Agriculture, S of' sub-row."),
    "00wek6x04_1965": ({"enr_women": 784, "fac_women": 69},
        "Re-read Women enrollment & faculty: use the CAMPUS row (5b), NOT the '-Agriculture, S of' sub-row."),
    "02w0trx84_1965": ({"fac_women": 80},
        "Re-read Women faculty. Bozeman = 'Montana State C' (row 7 in 1965); 'Montana State U' (row 8) is Missoula = today's U. of Montana."),
    "01sbq1a82_1939": ({"enr_women": 309},
        "The book splits U. Delaware over two rows: the men's row prints 0 women; the Women's College row prints 309. Convention: institution-wide total — confirm 309 and note 'includes Women's College'."),
    "02kyckx55_1950": ({"income": 1292},
        "Re-check income (you flagged the row-number confusion). Suggested reading pre-selected — confirm or correct."),
    "05p1j8758_1953": ({"enr_men": 344, "enr_women": 1121},
        "Re-check enrollment (you flagged it). Suggested readings pre-selected — confirm or correct."),
    "05p1j8758_1959": ({"fac_men": 12, "fac_women": 20},
        "Re-check faculty (you flagged it). Suggested readings pre-selected — confirm or correct."),
    "017zqws13_1950": ({"fac_men": 13, "fac_women": 98},
        "Re-check faculty (you flagged it). Suggested readings pre-selected — confirm or correct."),
    "004srrf86_1950": ({"fac_men": 52, "fac_women": 27},
        "Re-check faculty (you flagged the column transposition). Suggested readings pre-selected — confirm or correct."),
    "01zkghx44_1959": ({"enr_women": 33},
        "Re-check Women enrollment: 5,590 next to it is the MEN column. Suggested reading pre-selected."),
    "00scwqd12_1953": ({"enr_women": 30, "fac_women": 2},
        "Re-check (School of Mines row 46, not U. of Missouri row 36). Suggested readings pre-selected."),
    "00scwqd12_1956": ({"enr_women": 14},
        "Re-check (School of Mines row 74, not U. of Missouri). Suggested reading pre-selected."),
    "0464edn46_1953": ({"income": 300, "fac_women": 1},
        "Re-check: King's College = PA row 52 'Kings C' (Wilkes-Barre); row 89 is Penn State. Suggested readings pre-selected."),
    "05vzafd60_1939": ({"income": None},
        "Income cell previously read as dots '....' (not printed). Confirm → N/A (or type what you see)."),
    "04gr4te78_1950": ({"income": None, "enr_men": None, "enr_women": None, "fac_men": None, "fac_women": None},
        "Prior verification says this row prints completely BLANK. Confirm each column is blank → N/A each; note anything you do see."),
    "00j52pq61_1965": ({"income": None, "enr_men": 1611, "enr_women": 288, "fac_men": 412, "fac_women": 26},
        "Use row 37a '-Agriculture, NY State C of' under Cornell — NOT the SUNY duplicate row 174f(1), NOT the parent Cornell row. Income prints ‡ (= included with parent) → N/A + note."),
}

ALERT_JOINT = (
    "Faculty prints as ONE combined number (no men/women split). Enter the total under Men "
    "(suggested value pre-selected), mark Women N/A, and write 'reported jointly' in the notes."
)
JOINT = {  # item -> combined faculty total (goes to fac_men as current candidate)
    "000e0be47_1956": 1588, "000e0be47_1959": 1534, "000e0be47_1962": 1943,
    "0072zz521_1956": 377, "0072zz521_1959": 373, "0072zz521_1962": 376,
    "00f54p054_1962": 1973, "00hj8s172_1953": 3301, "00hj8s172_1956": 2673,
    "00hj8s172_1962": 3809, "00hj8s172_1965": 3809, "00jmfr291_1953": 1191,
    "00ysfqy60_1959": 497, "00za53h95_1959": 257, "017zqws13_1956": 1267,
    "017zqws13_1959": 2366, "0190ak572_1959": 3980, "01an7q238_1939": 1755,
    "022kthw22_1953": 432, "022kthw22_1956": 926, "022kthw22_1962": 414,
    "024mw5h28_1956": 775, "024mw5h28_1962": 860, "024mw5h28_1965": 860,
    "02b6qw903_1965": 453, "02ttsq026_1959": 541, "02ttsq026_1962": 541,
    "0324fzh77_1959": 87, "03taz7m60_1959": 1288, "03taz7m60_1962": 1346,
    "03vek6s52_1953": 2752, "03vek6s52_1956": 3070, "043mer456_1956": 544,
    "046rm7j60_1939": 1755, "049s0rh22_1959": 303, "05jbt9m15_1959": 49,
    "05p1j8758_1965": 552, "05qwgg493_1956": 4100, "03r0ha626_1953": 562,
    "00cvxb145_1956": 900, "00cvxb145_1959": 1000, "01yc7t268_1959": 1721,
    "05h7xva58_1965": 153, "011vxgd24_1962": 797,
}
JOINT_UC1939 = {"01an7q238_1939", "046rm7j60_1939"}  # combined "University of California" listing

# units revert: preserved value ×1000 -> as printed (items stay done)
UNITS_REVERT = {  # item -> (shipped, printed)
    "03taz7m60_1947": (7000, 7), "03v76x132_1965": (52000, 52), "049s0rh22_1962": (14000, 14),
    "04w7skc03_1947": (3000, 3), "05dxps055_1953": (12000, 12), "05g3dte14_1965": (14000, 14),
    "00cvxb145_1950": (13000, 13), "02vm5rt34_1956": (6000, 6), "02smfhw86_1956": (12000, 12),
}
INSTITUTION = {}  # filled from dataset

# ---------------------------------------------------------------- helpers
def fields_of(item):
    for sec in item["sections"]:
        for f in sec["fields"]:
            yield f

def field(item, key):
    for f in fields_of(item):
        if f["key"] == key:
            return f
    raise KeyError(f"{item['id']}.{key}")

def clean_note(note):
    """Strip the pass-2 machine-appended income fragments, keep the RA's own text."""
    if not note:
        return note
    for marker in (" | income: not printed in book", " | income corrected from scan",
                   "income: not printed in book", "income corrected from scan"):
        idx = note.find(marker)
        if idx >= 0:
            note = note[:idx].rstrip(" |")
    return note

# ---------------------------------------------------------------- load
ds = json.load(open(BASE_DS))
items = {it["id"]: it for it in ds["items"]}
INSTITUTION.update({iid: it["title"] for iid, it in items.items()})
p = json.load(open(V2))
res = p["results"]

reopened_cells = 0
# ---- A. blind reopens ----
for iid, (fks, extra) in BLIND.items():
    it = items[iid]
    it["alert"] = ALERT_INCOME_BLIND + extra
    for fk in fks:
        f = field(it, fk)
        f["candidates"] = [c for c in f["candidates"] if c.get("ref")]  # keep reference chips only
        f["agree"] = False
        f["default"] = None
        r = res.get(iid)
        if r and fk in r.get("fields", {}):
            del r["fields"][fk]
            reopened_cells += 1
    if iid in res:
        res[iid]["notes"] = clean_note(res[iid].get("notes"))

# ---- B. confirm reopens ----
for iid, (prefill, alert) in CONFIRM.items():
    it = items[iid]
    it["alert"] = alert
    for fk, val in prefill.items():
        f = field(it, fk)
        if val is not None:
            f["candidates"] = [c for c in f["candidates"] if c.get("ref") or c["source"] != "current"]
            f["candidates"].insert(0, {"source": "current", "value": val})
            f["default"] = "current"
            f["agree"] = False
        else:
            f["default"] = None
        r = res.get(iid)
        if r and fk in r.get("fields", {}):
            del r["fields"][fk]
            reopened_cells += 1
    if iid in res:
        res[iid]["notes"] = clean_note(res[iid].get("notes"))

# ---- C. joint-faculty reopens ----
for iid, total in JOINT.items():
    it = items[iid]
    extra = (" NOTE: 1939 prints ONE combined 'University of California' entry — this is the combined UC total; "
             "also note 'combined UC listing'.") if iid in JOINT_UC1939 else ""
    # don't clobber a more specific alert set above
    it["alert"] = (it.get("alert") + " " if it.get("alert") else "") + ALERT_JOINT + extra
    f = field(it, "fac_men")
    f["candidates"] = [c for c in f["candidates"] if c.get("ref") or c["source"] != "current"]
    f["candidates"].insert(0, {"source": "current", "value": total})
    f["default"] = "current"
    f["agree"] = False
    r = res.get(iid)
    for fk in ("fac_men", "fac_women"):
        if r and fk in r.get("fields", {}):
            del r["fields"][fk]
            reopened_cells += 1

# ---- D. units revert (stay done) ----
units_rows = []
for iid, (shipped, printed) in UNITS_REVERT.items():
    r = res[iid]
    fv = r["fields"]["income"]
    assert fv.get("value") == shipped, (iid, fv)
    fv["choice"] = "custom"
    fv["value"] = printed
    fv["custom"] = str(printed)
    r["notes"] = (clean_note(r.get("notes")) or "").rstrip()
    r["notes"] = (r["notes"] + " | income as printed (filed in $ millions) — ×1000 applied downstream, see units flag").strip(" |")
    yr = int(iid.rsplit("_", 1)[1])
    units_rows.append([iid, INSTITUTION[iid], yr, printed, "millions", printed * 1000])

# ---- statuses on reopened records ----
REOPEN_IDS = set(BLIND) | set(CONFIRM) | set(JOINT)
for iid in REOPEN_IDS:
    r = res.get(iid)
    if not r:
        continue
    n_left = sum(1 for fv in r.get("fields", {}).values() if fv.get("choice"))
    r["status"] = "in_progress" if n_left > 0 else "untouched"

# ---------------------------------------------------------------- write
out_scratch = Path(SCRATCH) / "dataset_pass3.json"
out_scratch.write_text(json.dumps(ds))
try:
    REPO_DS.write_text(json.dumps(ds))
    repo_note = str(REPO_DS)
except Exception as e:  # OneDrive hiccup — scratch copy is authoritative for shipping
    repo_note = f"REPO WRITE FAILED: {e}"

json.dump(p, open(V3, "w"))

with open(Path(SCRATCH) / "income_units_flags.csv", "w", newline="") as fcsv:
    w = csv.writer(fcsv)
    w.writerow(["item_id", "institution", "year", "income_as_printed", "filed_unit", "income_thousands_for_panel"])
    w.writerows(sorted(units_rows))

# ---------------------------------------------------------------- report
from collections import Counter
st = Counter(r.get("status") for r in res.values())
print(f"reopened items: {len(REOPEN_IDS)} (blind {len(BLIND)}, confirm {len(CONFIRM)}, joint {len(JOINT)})")
print(f"reopened cells: {reopened_cells}")
print(f"alerts set: {sum(1 for it in ds['items'] if it.get('alert'))}")
print(f"units reverted: {len(UNITS_REVERT)}")
print(f"v3 statuses: {dict(st)}")
print(f"dataset -> {out_scratch} ; {repo_note}")
print(f"preserved v3 -> {V3}")
