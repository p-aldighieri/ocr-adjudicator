#!/usr/bin/env python3
"""
build_dataset.py — turn the College Blue Book covariate panels + page scans into a
single self-contained dataset the OCR-Adjudicator web app consumes.

Outputs (default into ../public/dataset):
  dataset.json        normalized items -> sections -> fields -> candidate values + overlay boxes
  images/<id>.webp    recompressed page scans / snippets (deduped, shared full pages written once)

Overlay boxes (value box per source, row band, column band) are generated offline with RapidOCR
by matching each model's printed value back to a word box on the scan. No pre-existing coordinate
data is required.

This script is dataset-specific (it knows the Blue Book manifest layout), but its OUTPUT format is
generic, so the app itself is a general OCR-adjudication tool.

Usage:
  python build_dataset.py                         # all years, all unis, OCR snippets
  python build_dataset.py --years 1962 1939 --limit 8   # quick prototype subset
  python build_dataset.py --no-ocr                # skip overlay generation (fast)
  python build_dataset.py --ocr-full              # also OCR full pages (slow; for no-snippet years)
  python build_dataset.py --zip                   # also emit dataset.zip for phone import
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, os, sys, statistics, zipfile
from pathlib import Path

# ----------------------------------------------------------------------------- config / paths
PANELS = Path(r"C:\Users\dep89\Dropbox\Computers and Science\Data\Processed data\College Blue Books\covariate_panels")
TMP = Path(r"C:\Users\dep89\Dropbox\Computers and Science\Computers-and-Science\tmp\funding_expansion")
HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent / "public" / "dataset"
OCR_CACHE = HERE / ".ocr_cache.json"

YEARS = [1939, 1947, 1950, 1953, 1956, 1959, 1962, 1965]
SNIPPET_YEARS = {1953, 1956, 1959, 1962, 1965}

# WebP recompression targets
SNIP_MAXW = 1800     # snippets are wide+short; keep detail
FULL_MAXSIDE = 1700  # full pages (fallback view; crops are taken from the original, not this)
SNIP_Q = 80
FULL_Q = 78

# ----------------------------------------------------------------------------- small helpers
def norm_num(v):
    """Return canonical numeric string for a CSV value, or None for blank/nan."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else str(f)
    except ValueError:
        d = "".join(ch for ch in s if ch.isdigit())
        return d or None

def num_or_none(v):
    s = norm_num(v)
    if s is None:
        return None
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        return None

def digits(s):
    return "".join(ch for ch in str(s) if ch.isdigit())

def load_csv(path):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {row["ror_id"]: row for row in csv.DictReader(f)}

def short_id(*parts):
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return h[:12]

def _norm_name(s):
    return "".join(c for c in str(s).lower() if c.isalnum())

_mw_cache = {}

def _ni(v):
    x = num_or_none(v)
    return int(x) if x is not None else None

def early_mw(year):
    """For 1939/47/50, recover men/women faculty & enrollment from the raw extraction JSONs.
    Joined on (state, printed institution number) — the BB's own index — which is reliable
    (the panel's recorded cl_name/cx_name are sometimes mis-matched). Returns {ror: {cl,cx}}."""
    if year in _mw_cache:
        return _mw_cache[year]
    man = load_csv(PANELS / f"manifest_{year}.csv")

    def index(meth):
        idx = {}
        p = TMP / f"all_{year}_{meth}.json"
        if p.exists():
            for r in json.loads(p.read_text(encoding="utf-8")):
                idx.setdefault((_norm_name(r.get("state")), _ni(r.get("n"))), r)
        return idx

    ecl, ecx = index("claude"), index("codex")
    res = {}
    for ror, row in man.items():
        k = (_norm_name(row.get("state")), _ni(row.get("inst_number")))
        cl = ecl.get(k) or {}
        cx = ecx.get(k) or {}
        res[ror] = {
            "cl": {"fac_m": cl.get("faculty_men"), "fac_w": cl.get("faculty_women"),
                   "enr_m": cl.get("enr_men"), "enr_w": cl.get("enr_women")},
            "cx": {"fac_m": cx.get("faculty_men"), "fac_w": cx.get("faculty_women"),
                   "enr_m": cx.get("enr_men"), "enr_w": cx.get("enr_women")},
        }
    _mw_cache[year] = res
    return res

# ----------------------------------------------------------------------------- OCR
_engine = None
_ocr_cache = None

def ocr_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine

def load_ocr_cache():
    global _ocr_cache
    if _ocr_cache is None:
        if OCR_CACHE.exists():
            _ocr_cache = json.loads(OCR_CACHE.read_text())
        else:
            _ocr_cache = {}
    return _ocr_cache

def save_ocr_cache():
    if _ocr_cache is not None:
        try:
            OCR_CACHE.write_text(json.dumps(_ocr_cache))
        except OSError as e:
            print(f"  (cache write skipped: {e})")

def _tokens_from_result(res):
    tokens = []
    for box, txt, score in (res or []):
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        tokens.append({"t": str(txt), "x0": min(xs), "y0": min(ys),
                       "x1": max(xs), "y1": max(ys), "s": float(score)})
    return tokens

def get_tokens(src_path):
    """OCR a source image file (cached by path). Returns (tokens, (W,H)) in source pixels."""
    cache = load_ocr_cache()
    key = str(src_path)
    if key in cache:
        c = cache[key]
        return c["tokens"], (c["w"], c["h"])
    from PIL import Image
    W, H = Image.open(src_path).size
    tokens = _tokens_from_result(ocr_engine()(str(src_path))[0])
    cache[key] = {"w": W, "h": H, "tokens": tokens}
    return tokens, (W, H)

def get_tokens_pil(key, pil):
    """OCR an in-memory PIL image (cached by an explicit key). Returns (tokens, (W,H))."""
    import numpy as np
    cache = load_ocr_cache()
    if key in cache:
        c = cache[key]
        return c["tokens"], (c["w"], c["h"])
    W, H = pil.size
    arr = np.array(pil.convert("RGB"))
    tokens = _tokens_from_result(ocr_engine()(arr)[0])
    cache[key] = {"w": W, "h": H, "tokens": tokens}
    return tokens, (W, H)

def boxes_from_tokens(tokens, W, H, want_by_field, anchor_values, force_full_row=False):
    """want_by_field: {field_key: {source: numeric_string}} for the values we want boxed.
    anchor_values: set of numeric strings used to locate the institution's row.
    force_full_row: when the image is already a single-row crop, treat the whole image as the row.
    Returns: (row_band or None, boxes list). Coords NORMALIZED 0..1 to the image."""
    if not tokens or W == 0 or H == 0:
        return None, []

    # locate institution row: cluster value-matching tokens by y, pick densest distinct cluster
    matches = []
    for tk in tokens:
        td = digits(tk["t"])
        if len(td) >= 2 and td in anchor_values:
            matches.append((td, (tk["y0"] + tk["y1"]) / 2.0, tk))
    row_band = None
    grp = []
    if matches:
        heights = [t["y1"] - t["y0"] for _, _, t in matches]
        tol = (statistics.median(heights) or 20) * 0.9
        best = None
        for _, yc, _ in matches:
            g = [m for m in matches if abs(m[1] - yc) <= tol]
            distinct = len(set(m[0] for m in g))
            if best is None or distinct > best[0]:
                best = (distinct, yc, g)
        _, yc, grp = best
        y0 = min(m[2]["y0"] for m in grp)
        y1 = max(m[2]["y1"] for m in grp)
        pad = (y1 - y0) * 0.25
        row_band = {"y": max(0.0, (y0 - pad) / H), "h": min(1.0, (y1 - y0 + 2 * pad) / H)}
    if force_full_row and row_band is None:
        row_band = {"y": 0.08, "h": 0.84}

    def in_band(tk):
        if row_band is None:
            return True
        yc = (tk["y0"] + tk["y1"]) / 2.0 / H
        return row_band["y"] - 0.01 <= yc <= row_band["y"] + row_band["h"] + 0.01

    boxes = []
    for fkey, by_src in want_by_field.items():
        for source, val in by_src.items():
            if not val:
                continue
            cand = [tk for tk in tokens if digits(tk["t"]) == val and len(val) >= 2 and in_band(tk)]
            if not cand and row_band is not None:
                cand = [tk for tk in tokens if digits(tk["t"]) == val and len(val) >= 2]
            if not cand:
                continue
            # prefer the box nearest the row centre
            if row_band is not None:
                cy = (row_band["y"] + row_band["h"] / 2.0) * H
                cand.sort(key=lambda tk: abs((tk["y0"] + tk["y1"]) / 2.0 - cy))
            tk = cand[0]
            boxes.append({
                "field": fkey, "source": source,
                "x": tk["x0"] / W, "y": tk["y0"] / H,
                "w": (tk["x1"] - tk["x0"]) / W, "h": (tk["y1"] - tk["y0"]) / H,
            })
    return row_band, boxes

def find_row_and_boxes(src_path, want_by_field, anchor_values):
    """OCR a source file and box values on it (used for the pre-made snippet years)."""
    try:
        tokens, (W, H) = get_tokens(src_path)
    except Exception as e:
        print(f"    ! OCR failed for {src_path}: {e}")
        return None, []
    return boxes_from_tokens(tokens, W, H, want_by_field, anchor_values)

# ----------------------------------------------------------------------------- row location (no-snippet years)
def _theil_sen(pairs):
    """Robust line fit y = a*x + b from (x,y) pairs. Returns (a,b) or None."""
    slopes = []
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            if pairs[j][0] != pairs[i][0]:
                slopes.append((pairs[j][1] - pairs[i][1]) / (pairs[j][0] - pairs[i][0]))
    if not slopes:
        return None
    a = statistics.median(slopes)
    b = statistics.median([y - a * x for x, y in pairs])
    return a, b

def locate_row(src_path, n):
    """Find the y-centre and row pitch of institution number `n` using the leftmost
    number column of a ruled table page. OCRs only a narrow left strip (fast).
    Returns (yc, pitch, W, H) or None."""
    if n is None:
        return None
    from PIL import Image
    try:
        full = Image.open(src_path)
        W, H = full.size
        strip = full.convert("RGB").crop((0, 0, int(W * 0.16), H))  # x starts at 0 => coords match page
        tokens, _ = get_tokens_pil("leftcol:" + str(src_path), strip)
    except Exception:
        return None
    if not tokens:
        return None
    n = int(round(float(n)))
    left = []
    for tk in tokens:
        xc = (tk["x0"] + tk["x1"]) / 2.0
        d = digits(tk["t"])
        if xc < 0.14 * W and 1 <= len(d) <= 3:
            try:
                left.append((int(d), (tk["y0"] + tk["y1"]) / 2.0))
            except ValueError:
                pass
    if len(left) < 3:
        return None
    fit = _theil_sen(left)
    if not fit:
        return None
    a, b = fit
    if a <= 0:                       # numbers must increase downward
        return None
    direct = [y for num, y in left if num == n]
    pred = a * n + b
    yc = direct[0] if direct and abs(direct[0] - pred) < 1.5 * a else pred
    if yc < 0 or yc > H:
        return None
    return yc, a, W, H

def row_crop_window(page_src, n, context_rows=3.3):
    """Pixel window (y0,y1,yc,pitch,W,H) for a readable crop centred on institution `n`'s row
    (~context_rows above & below for context), or None. Shared by build_item and the prewarm so
    crop ids match exactly."""
    loc = locate_row(page_src, n)
    if not loc:
        return None
    yc, pitch, W, H = loc
    half = max(40.0, pitch * context_rows)
    y0 = max(0, int(yc - half)); y1 = min(H, int(yc + half))
    if y1 - y0 < 24:
        return None
    return y0, y1, yc, pitch, W, H

_img_registry = {}  # src_path -> {id, file, w, h}
_pil_registry = {}  # crop-id -> rec

def register_image(out_dir, src_path, role, side, label):
    """Convert src image to webp once (deduped by src path); return image descriptor.
    Skips re-encoding if the webp already exists (fast re-runs)."""
    from PIL import Image
    src_path = str(src_path)
    if src_path in _img_registry:
        d = dict(_img_registry[src_path]); d.update(role=role, side=side, label=label)
        return d
    if not os.path.exists(src_path):
        return None
    iid = short_id(src_path)
    fpath = out_dir / "images" / f"{iid}.webp"
    w, h = Image.open(src_path).size          # ORIGINAL dims (cheap; needed for box coords)
    if not fpath.exists():
        im = Image.open(src_path).convert("RGB")
        maxside = SNIP_MAXW if role == "snippet" else FULL_MAXSIDE
        if max(w, h) > maxside:
            s = maxside / max(w, h)
            im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
        fpath.parent.mkdir(parents=True, exist_ok=True)
        im.save(fpath, "WEBP", quality=SNIP_Q if role == "snippet" else FULL_Q, method=4)
    rec = {"id": iid, "file": f"images/{fpath.name}", "w": w, "h": h}
    _img_registry[src_path] = rec
    d = dict(rec); d.update(role=role, side=side, label=label)
    return d

def register_crop(out_dir, pil_crop, iid, side, label):
    """Register an in-memory crop (a generated per-row snippet) as a snippet image."""
    from PIL import Image  # noqa: F401
    rec = _pil_registry.get(iid)
    if rec is None:
        fpath = out_dir / "images" / f"{iid}.webp"
        w, h = pil_crop.size
        if not fpath.exists():
            im = pil_crop.convert("RGB")
            if w > SNIP_MAXW:
                s = SNIP_MAXW / w
                im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
            fpath.parent.mkdir(parents=True, exist_ok=True)
            im.save(fpath, "WEBP", quality=SNIP_Q, method=4)
        rec = {"id": iid, "file": f"images/{fpath.name}", "w": w, "h": h}
        _pil_registry[iid] = rec
    d = dict(rec); d.update(role="snippet", side=side, label=label)
    return d

# ----------------------------------------------------------------------------- field/section model
def make_candidates(claude, codex, current, refs=None):
    cands = []
    if claude is not None:
        cands.append({"source": "claude", "value": claude})
    if codex is not None:
        cands.append({"source": "codex", "value": codex})
    if current is not None and current not in (claude, codex):
        cands.append({"source": "current", "value": current})
    for r in (refs or []):
        if r["value"] is not None:
            cands.append(r)
    return cands

def field(key, label, claude, codex, current, image_id, refs=None, flags=None):
    cl = num_or_none(claude); cx = num_or_none(codex); cur = num_or_none(current)
    agree = cl is not None and cl == cx
    default = None
    if agree:
        default = "claude"
    elif cl is not None and cx is None:
        default = "claude"
    elif cx is not None and cl is None:
        default = "codex"
    return {
        "key": key, "label": label, "imageId": image_id,
        "candidates": make_candidates(cl, cx, cur, refs),
        "agree": agree, "default": default,
        "flags": flags or [],
        # normalized digit strings used by the OCR matcher
        "_match": {"claude": digits(cl) if cl is not None else "",
                   "codex": digits(cx) if cx is not None else ""},
    }

# ----------------------------------------------------------------------------- per-year item build
def build_item(out_dir, year, ror, man, cmp_, do_ocr, ocr_full):
    uni = man.get("university") or cmp_.get("university") or ror
    state = man.get("state", "")
    n = man.get("n") or man.get("inst_number") or ""
    iid = f"{ror.split('/')[-1]}_{year}"

    # --- resolve images per year layout ---
    imgs = {}        # side -> descriptor
    src_by_side = {} # side -> source path
    def reg(col, role, side, label):
        p = man.get(col, "")
        if p and p.strip() and p.strip().lower() != "nan":
            d = register_image(out_dir, p.strip(), role, side, label)
            if d:
                imgs[side] = d
                src_by_side[side] = p.strip()
                return d["id"]
        return None

    income_img = enr_img = fac_img = None
    image_list = []
    if year == 1953:
        sid = reg("snippet", "snippet", "S", "Row snippet")
        fid = reg("full", "full", "F", f"Full page {man.get('spread','')}")
        income_img = enr_img = fac_img = sid or fid
    elif year in (1956, 1959, 1962, 1965):
        ls = reg("L_snippet", "snippet", "L", "Left snippet — enrollment & faculty")
        rs = reg("R_snippet", "snippet", "R", "Right snippet — income")
        reg("L_full", "full", "Lf", f"Left full page")
        reg("R_full", "full", "Rf", f"Right full page")
        income_img = rs
        enr_img = fac_img = ls
    elif year == 1939:
        names = reg("names_image", "full", "L", "Names page (Table A)")
        res = reg("resources_image", "full", "R", "Numbers page (Table D-right)")
        income_img = enr_img = fac_img = res
    elif year in (1947, 1950):
        gs = reg("gs_image", "full", "L", "GS page (faculty)")
        res = reg("res_image", "full", "R", "RES page (income / enrollment)")
        income_img = enr_img = res
        fac_img = gs
    # ordered, de-duped image list for the viewer
    seen = set()
    for side in ("S", "L", "R", "Lf", "Rf", "F"):
        if side in imgs and imgs[side]["id"] not in seen:
            seen.add(imgs[side]["id"])
            image_list.append({k: imgs[side][k] for k in ("id", "file", "w", "h", "role", "side", "label")})

    # --- candidate sources (compare files have cx_/cl_ for all years) ---
    cx_inc = cmp_.get("cx_income"); cl_inc = cmp_.get("cl_income")
    cx_fac = cmp_.get("cx_fac");     cl_fac = cmp_.get("cl_fac")
    cx_enr = cmp_.get("cx_enr");     cl_enr = cmp_.get("cl_enr")
    final_income = man.get("final_income")
    final_fac = man.get("final_faculty")
    final_enr = man.get("final_enrollment")
    income_conf = (man.get("final_income_confident", "") or "").strip().lower() == "true"
    lg_inc = cmp_.get("lg_income") or man.get("landgrant_income")
    q_inc = cmp_.get("q_income")

    sections = []
    # INCOME ----------------------------------------------------------------
    refs = []
    if num_or_none(lg_inc) is not None:
        refs.append({"source": "landgrant", "value": num_or_none(lg_inc), "ref": True})
    if num_or_none(q_inc) is not None:
        refs.append({"source": "quincy", "value": num_or_none(q_inc), "ref": True})
    inc = field("income", "Income", cl_inc, cx_inc, final_income, income_img, refs=refs)
    inc["confident"] = income_conf
    inc["unit"] = "$ thousands"
    sections.append({"key": "income", "label": "Income ($ thousands)", "fields": [inc]})

    if year in SNIPPET_YEARS:
        # ENROLLMENT m/w
        e_m = field("enr_men", "Men", man.get("claude_enr_m"), man.get("codex_enr_m"), None, enr_img)
        e_w = field("enr_women", "Women", man.get("claude_enr_w"), man.get("codex_enr_w"), None, enr_img)
        sections.append({"key": "enrollment", "label": "Enrollment", "total": num_or_none(final_enr),
                         "fields": [e_m, e_w]})
        # FACULTY m/w
        f_m = field("fac_men", "Men", man.get("claude_fac_m"), man.get("codex_fac_m"), None, fac_img,
                    flags=["weak"])
        f_w = field("fac_women", "Women", man.get("claude_fac_w"), man.get("codex_fac_w"), None, fac_img,
                    flags=["weak"])
        sections.append({"key": "faculty", "label": "Faculty", "total": num_or_none(final_fac),
                         "fields": [f_m, f_w]})
    else:
        # 1939/47/50: men/women restored from the raw extraction (joined via cl_name/cx_name)
        mw = early_mw(year).get(ror, {})
        cl = mw.get("cl", {}); cx = mw.get("cx", {})
        enr_flags = ["unreliable"] if year in (1947, 1950) else []
        e_m = field("enr_men", "Men", cl.get("enr_m"), cx.get("enr_m"), None, enr_img, flags=enr_flags)
        e_w = field("enr_women", "Women", cl.get("enr_w"), cx.get("enr_w"), None, enr_img, flags=enr_flags)
        sections.append({"key": "enrollment", "label": "Enrollment", "total": num_or_none(final_enr),
                         "fields": [e_m, e_w]})
        f_m = field("fac_men", "Men", cl.get("fac_m"), cx.get("fac_m"), None, fac_img, flags=["weak"])
        f_w = field("fac_women", "Women", cl.get("fac_w"), cx.get("fac_w"), None, fac_img, flags=["weak"])
        sections.append({"key": "faculty", "label": "Faculty", "total": num_or_none(final_fac),
                         "fields": [f_m, f_w]})

    # --- priority score ---
    prio = 0.0
    if not income_conf:
        prio += 0.5
    for sec in sections:
        for fl in sec["fields"]:
            cands = [c for c in fl["candidates"] if c["source"] in ("claude", "codex")]
            vals = {c["source"]: c["value"] for c in cands}
            if "claude" in vals and "codex" in vals and vals["claude"] != vals["codex"]:
                prio += 0.25 if fl["key"].startswith("income") else 0.15
            if not cands:
                prio += 0.05
    prio = min(1.0, round(prio, 3))

    # --- OCR overlay boxes (snippets first; full pages only with --ocr-full) ---
    overlays = {}   # imageId -> {row, boxes}
    if do_ocr:
        # anchor values to find the row = every numeric we know for this uni
        anchors = set()
        for cand_src in (final_income, final_fac, final_enr,
                         man.get("endowment_final"), man.get("tuition"),
                         cl_inc, cx_inc, cl_fac, cx_fac, cl_enr, cx_enr):
            d = digits(num_or_none(cand_src)) if num_or_none(cand_src) is not None else ""
            if len(d) >= 2:
                anchors.add(d)
        for sec in sections:
            for fl in sec["fields"]:
                for s in ("claude", "codex"):
                    if fl["_match"][s]:
                        anchors.add(fl["_match"][s])

        # --- no-snippet years: auto-crop a per-row snippet from the ruled full page ---
        def fget(k):
            for sec in sections:
                for fl in sec["fields"]:
                    if fl["key"] == k:
                        return fl
            return None

        def add_row_crop(page_src, fkeys, side, label):
            if not page_src:
                return
            win = row_crop_window(page_src, num_or_none(n))
            if not win:
                return
            y0, y1, yc, pitch, W, H = win
            from PIL import Image
            crop = Image.open(page_src).convert("RGB").crop((0, y0, W, y1))
            cid = "crop_" + short_id(page_src, num_or_none(n), y0, y1)
            desc = register_crop(out_dir, crop, cid, side, label)
            ch = max(1, y1 - y0)
            band = {"y": max(0.0, (yc - 0.55 * pitch - y0) / ch), "h": min(1.0, (pitch * 1.1) / ch)}
            want = {k: dict(fget(k)["_match"]) for k in fkeys if fget(k)}
            tk, (tw, th) = get_tokens_pil("crop:" + cid, crop)
            _, boxes = boxes_from_tokens(tk, tw, th, want, anchors)
            overlays[desc["id"]] = {"row": band, "boxes": boxes}
            for k in fkeys:
                fl = fget(k)
                if fl:
                    fl["imageId"] = desc["id"]
            image_list.insert(0, {kk: desc[kk] for kk in ("id", "file", "w", "h", "role", "side", "label")})

        if year == 1939:
            add_row_crop(src_by_side.get("R"), ["income", "enr_men", "enr_women", "fac_men", "fac_women"],
                         "S", "Row snippet (auto-cropped)")
        elif year in (1947, 1950):
            add_row_crop(src_by_side.get("R"), ["income", "enr_men", "enr_women"], "S", "Row snippet — income / enrollment")
            add_row_crop(src_by_side.get("L"), ["fac_men", "fac_women"], "Sf", "Row snippet — faculty")

        # group fields by the image they sit on
        by_image = {}
        for sec in sections:
            for fl in sec["fields"]:
                if not fl["imageId"]:
                    continue
                by_image.setdefault(fl["imageId"], {})[fl["key"]] = dict(fl["_match"])
        # map imageId -> src path & role
        id2src = {}
        for src, rec in _img_registry.items():
            id2src[rec["id"]] = (src, rec)
        for image_id, want in by_image.items():
            src, rec = id2src.get(image_id, (None, None))
            if not src:
                continue
            role = next((im["role"] for im in image_list if im["id"] == image_id), "full")
            if role != "snippet" and not ocr_full:
                continue
            row, boxes = find_row_and_boxes(src, want, anchors)
            if row or boxes:
                overlays[image_id] = {"row": row, "boxes": boxes}

    # strip internal match helper
    for sec in sections:
        for fl in sec["fields"]:
            fl.pop("_match", None)

    return {
        "id": iid, "groupKey": ror, "group": uni, "title": uni.title() if uni else iid,
        "subtitle": (state or "").title(), "year": year, "n": num_or_none(n),
        "priority": prio, "images": image_list, "sections": sections, "overlays": overlays,
    }

# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="*", default=YEARS)
    ap.add_argument("--limit", type=int, default=0, help="max unis per year (0 = all)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--ocr-full", action="store_true", help="also OCR full pages (slow)")
    ap.add_argument("--zip", action="store_true")
    args = ap.parse_args()

    out = args.out
    (out / "images").mkdir(parents=True, exist_ok=True)
    do_ocr = not args.no_ocr

    items = []
    for year in args.years:
        man = load_csv(PANELS / f"manifest_{year}.csv")
        cmp_ = load_csv(PANELS / f"compare_{year}.csv")
        rors = list(man.keys())
        if args.limit:
            rors = rors[: args.limit]
        print(f"[{year}] {len(rors)} institutions ...")
        for i, ror in enumerate(rors, 1):
            it = build_item(out, year, ror, man[ror], cmp_.get(ror, {}), do_ocr, args.ocr_full)
            items.append(it)
            if i % 25 == 0:
                print(f"    {i}/{len(rors)}")
                save_ocr_cache()
        save_ocr_cache()

    # group ordering: by institution name, year ascending
    items.sort(key=lambda it: (it["group"], it["year"]))

    dataset = {
        "meta": {
            "name": "College Blue Books",
            "schema": 1,
            "covariateNote": "Income in $ thousands. Faculty/enrollment are head counts.",
            "years": sorted(set(it["year"] for it in items)),
            "nItems": len(items),
            "sources": ["claude", "codex", "current", "landgrant", "quincy"],
        },
        "items": items,
    }
    (out / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    n_imgs = len(list((out / "images").glob("*.webp")))
    size_mb = sum(f.stat().st_size for f in (out / "images").glob("*.webp")) / 1e6
    n_boxes = sum(len(ov["boxes"]) for it in items for ov in it["overlays"].values())
    n_rows = sum(1 for it in items for ov in it["overlays"].values() if ov.get("row"))
    print(f"\nWROTE {out/'dataset.json'}")
    print(f"  items={len(items)}  images={n_imgs} ({size_mb:.1f} MB)  overlay-boxes={n_boxes}  row-bands={n_rows}")

    if args.zip:
        zpath = out.parent / "dataset.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
            z.write(out / "dataset.json", "dataset.json")
            for f in (out / "images").glob("*.webp"):
                z.write(f, f"images/{f.name}")
        print(f"  zip={zpath} ({zpath.stat().st_size/1e6:.1f} MB)")

if __name__ == "__main__":
    main()
