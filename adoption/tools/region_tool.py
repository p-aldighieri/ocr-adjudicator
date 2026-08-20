#!/usr/bin/env python3
"""Region-pilot helper: grid overviews, batch crops, normalized-coordinate math.

All coordinates on the command line are NORMALIZED 0..1 (x0 y0 x1 y1).
"""
import json, os, sys
from PIL import Image, ImageDraw

BUILD = "/Users/p-aldighieri/GitHub/ocr-adjudicator/adoption/dataset-build"
TMP = "/private/tmp/claude-501/-Users-p-aldighieri-GitHub-ocr-adjudicator/0adaa250-23ce-4cd9-b167-e54ccb3e6a11/scratchpad/regions_tmp"
os.makedirs(TMP, exist_ok=True)

_ds = None
def ds():
    global _ds
    if _ds is None:
        _ds = json.load(open(os.path.join(BUILD, "dataset.ground-truth.json")))
    return _ds

def item(iid):
    for it in ds()["items"]:
        if it["id"] == iid:
            return it
    raise SystemExit("no item " + iid)

def ref(iid, evid):
    for ev in item(iid)["evidence"]:
        if ev["id"] == evid:
            return ev
    raise SystemExit("no ref " + evid)

def img(iid, evid):
    ev = ref(iid, evid)
    return Image.open(os.path.join(BUILD, ev["file"])).convert("RGB"), ev


def cmd_info(iid):
    it = item(iid)
    print(f"== {it['id']} | {it.get('state')} {it.get('year')} | {it.get('title')}")
    print(f"   note: {(it.get('note') or '')[:300]}")
    for ev in it["evidence"]:
        if ev.get("role") in ("image", "pdf_page") and ev.get("file"):
            p = os.path.join(BUILD, ev["file"])
            w, h = Image.open(p).size
            print(f"  [{ev['id']}] {ev.get('sourceKind')}/{ev.get('layout')} {w}x{h} regions={len(ev.get('regions') or [])}")
            print(f"        line: {(ev.get('sourceLine') or '')[:150]}")
            print(f"        text: {(ev.get('text') or '')[:400]}")
    print("  BOOKS:")
    for b in it.get("books", []):
        print(f"    {b['key']}  ::  {b.get('title_as_stated')}")


def _grid(im, cells=10, label_every=1):
    """Overlay a labelled normalized grid. Columns 0..cells-1 left->right, rows likewise."""
    w, h = im.size
    d = ImageDraw.Draw(im)
    for i in range(1, cells):
        x = w * i / cells
        y = h * i / cells
        d.line([(x, 0), (x, h)], fill=(255, 0, 0), width=1)
        d.line([(0, y), (w, y)], fill=(0, 90, 255), width=1)
    for i in range(cells):
        x = w * (i + 0.5) / cells
        d.text((x - 6, 2), f"{i/cells:.1f}", fill=(255, 0, 0))
        y = h * (i + 0.5) / cells
        d.text((2, y - 5), f"{i/cells:.1f}", fill=(0, 90, 255))
    return im


def cmd_grid(iid, evid, cells=10, maxpx=1500):
    im, ev = img(iid, evid)
    w, h = im.size
    sc = min(1.0, maxpx / max(w, h))
    if sc < 1.0:
        im = im.resize((int(w * sc), int(h * sc)), Image.LANCZOS)
    _grid(im, cells)
    out = f"{TMP}/{iid}_{evid}_grid.png"
    im.save(out)
    print(out, f"(source {w}x{h}, shown {im.size[0]}x{im.size[1]})")


def _crop(iid, evid, x0, y0, x1, y1, name, minpx=1100, maxpx=1900, grid=False):
    im, ev = img(iid, evid)
    W, H = im.size
    box = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))
    c = im.crop(box)
    cw, ch = c.size
    if cw < 4 or ch < 4:
        print("crop too small", box); return None
    sc = 1.0
    if max(cw, ch) < minpx:
        sc = min(minpx / max(cw, ch), 4.0)
    if max(cw, ch) * sc > maxpx:
        sc = maxpx / max(cw, ch)
    if abs(sc - 1.0) > 0.02:
        c = c.resize((max(1, int(cw * sc)), max(1, int(ch * sc))), Image.LANCZOS)
    if grid:
        _grid(c, 10)
    out = f"{TMP}/{name}.png"
    c.save(out)
    print(f"{out}  norm=({x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f}) px={box} shown={c.size}")
    return out


def cmd_crop(iid, evid, *a):
    x0, y0, x1, y1 = map(float, a[:4])
    name = a[4] if len(a) > 4 else f"{iid}_{evid}_c"
    grid = len(a) > 5 and a[5] == "grid"
    _crop(iid, evid, x0, y0, x1, y1, name, grid=grid)


def cmd_batch(spec_path):
    """JSON list of {item,ev,x0,y0,x1,y1,name,grid?} -> many crops in one process."""
    for s in json.load(open(spec_path)):
        _crop(s["item"], s["ev"], s["x0"], s["y0"], s["x1"], s["y1"], s["name"], grid=s.get("grid", False))


def cmd_strips(iid, evid, n=4, overlap=0.02, x0=0.0, x1=1.0):
    n = int(n)
    for i in range(n):
        y0 = max(0.0, i / n - overlap)
        y1 = min(1.0, (i + 1) / n + overlap)
        _crop(iid, evid, x0, y0, x1, y1, f"{iid}_{evid}_s{i}", grid=True)


# ---------------- text-line detection (projection profile) ----------------
import numpy as np

def detect_lines(iid, evid, x0=0.0, x1=1.0, y0=0.0, y1=1.0, thresh=0.10, minh=3, gap=2):
    """Return list of (ny0, ny1) normalized bands of ink within the x-window."""
    im, ev = img(iid, evid)
    W, H = im.size
    g = np.asarray(im.convert("L"), dtype=np.float32)
    sub = g[int(y0*H):int(y1*H), int(x0*W):int(x1*W)]
    # local binarization against per-row-window background (median of the page)
    bg = np.median(sub)
    ink = (sub < bg - 28).astype(np.float32)
    prof = ink.mean(axis=1)
    on = prof > thresh * max(prof.max(), 1e-6) + 0.004
    bands = []
    i = 0
    n = len(on)
    while i < n:
        if on[i]:
            j = i
            while j + 1 < n and (on[j+1] or (j+1+gap < n and on[j+1:j+1+gap+1].any())):
                j += 1
            if j - i + 1 >= minh:
                bands.append((i, j))
            i = j + 1
        else:
            i += 1
    off = int(y0*H)
    return [((off+a)/H, (off+b+1)/H) for a, b in bands], (W, H)


def cmd_lines(iid, evid, x0=0.0, x1=1.0, y0=0.0, y1=1.0):
    x0, x1, y0, y1 = float(x0), float(x1), float(y0), float(y1)
    bands, (W, H) = detect_lines(iid, evid, x0, x1, y0, y1)
    print(f"{len(bands)} bands  page={W}x{H}")
    for k, (a, b) in enumerate(bands):
        print(f"  L{k:02d} y={a:.4f}..{b:.4f} (h={b-a:.4f})")


def cmd_sheet(iid, evid, x0=0.0, x1=1.0, y0=0.0, y1=1.0, pad=0.0015, cols=1, scale=1.6, name=None):
    """Contact sheet: each detected line cropped, numbered, stacked. One Read maps lines->titles."""
    x0, x1, y0, y1, pad, cols, scale = float(x0), float(x1), float(y0), float(y1), float(pad), int(cols), float(scale)
    bands, (W, H) = detect_lines(iid, evid, x0, x1, y0, y1)
    im, ev = img(iid, evid)
    cw = int((x1 - x0) * W)
    tiles = []
    for k, (a, b) in enumerate(bands):
        ta, tb = max(0.0, a - pad), min(1.0, b + pad)
        c = im.crop((int(x0*W), int(ta*H), int(x1*W), int(tb*H)))
        tiles.append((k, c, a, b))
    if not tiles:
        print("no lines"); return
    lab_w = 46
    tw = int(cw * scale)
    rows_per_col = (len(tiles) + cols - 1) // cols
    colw = tw + lab_w
    heights = []
    for ci in range(cols):
        chunk = tiles[ci*rows_per_col:(ci+1)*rows_per_col]
        heights.append(sum(int(t[1].size[1]*scale) + 6 for t in chunk))
    sheet = Image.new("RGB", (colw*cols, max(heights) + 10), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for ci in range(cols):
        chunk = tiles[ci*rows_per_col:(ci+1)*rows_per_col]
        yy = 5
        for (k, c, a, b) in chunk:
            ch = max(1, int(c.size[1]*scale))
            c2 = c.resize((tw, ch), Image.LANCZOS)
            sheet.paste(c2, (ci*colw + lab_w, yy))
            d.text((ci*colw + 4, yy + max(0, ch//2 - 5)), f"L{k:02d}", fill=(200, 0, 0))
            d.line([(ci*colw, yy+ch+3), (ci*colw+colw-4, yy+ch+3)], fill=(220, 220, 220))
            yy += ch + 6
    out = f"{TMP}/{name or (iid+'_'+evid+'_sheet')}.png"
    sheet.save(out)
    print(out, sheet.size, f"{len(tiles)} lines")
    for k, c, a, b in tiles:
        print(f"  L{k:02d} y={a:.4f}..{b:.4f}")




def tight_box(iid, evid, ny0, ny1, x0=0.0, x1=1.0, trim_dots=True, padx=0.006, pady=0.004):
    """Tight normalized bbox of ink in band [ny0,ny1] within x-window; trims leader dots."""
    im, ev = img(iid, evid)
    W, H = im.size
    g = np.asarray(im.convert("L"), dtype=np.float32)
    a, b = int(ny0*H), int(ny1*H)
    c0, c1 = int(x0*W), int(x1*W)
    sub = g[a:b, c0:c1]
    if sub.size == 0:
        return None
    bg = np.median(g)
    ink = sub < bg - 28
    colcount = ink.sum(axis=0)
    bandh = max(1, b - a)
    present = colcount > 0
    if not present.any():
        return None
    idx = np.where(present)[0]
    s, e = int(idx[0]), int(idx[-1])
    if trim_dots:
        # walk in from the right while columns are "dot-like": ink confined to the
        # lower part of the band (leader dots, rules) rather than real glyphs.
        topcut = int(0.55 * bandh)
        while e > s:
            col = ink[:topcut, e]
            if col.any():
                break
            e -= 1
    rows = np.where(ink[:, s:e+1].sum(axis=1) > 0)[0]
    ra, rb = (rows[0], rows[-1]) if len(rows) else (0, bandh - 1)
    nx0 = (c0 + s) / W - padx
    nx1 = (c0 + e + 1) / W + padx
    nyy0 = (a + ra) / H - pady
    nyy1 = (a + rb + 1) / H + pady
    return (max(0.0, nx0), max(0.0, nyy0), min(1.0, nx1), min(1.0, nyy1))


def cmd_boxes(iid, evid, x0, x1, y0, y1, idxs, trim="1"):
    """Print tight boxes for the given detected-line indices (comma list)."""
    x0, x1, y0, y1 = float(x0), float(x1), float(y0), float(y1)
    bands, (W, H) = detect_lines(iid, evid, x0, x1, y0, y1)
    for spec in idxs.split(","):
        if "-" in spec:  # merge a range of lines into one box (wrapped titles)
            p, q = spec.split("-"); p, q = int(p), int(q)
            lo, hi = bands[p][0], bands[q][1]
        else:
            p = int(spec); lo, hi = bands[p]
        tb = tight_box(iid, evid, lo, hi, x0, x1, trim_dots=(trim == "1"))
        if not tb:
            print(f"L{spec}: no ink"); continue
        a, b, c, d = tb
        print(f'L{spec}: x={a:.3f} y={b:.3f} w={c-a:.3f} h={d-b:.3f}   (box {a:.3f},{b:.3f},{c:.3f},{d:.3f})')


def cmd_verify(spec_path, name="verify", scale=1.5, maxw=1500):
    """Crop every planned box and stack them with the intended title text alongside.
    One Read then confirms content for a whole page (or whole batch)."""
    scale = float(scale); maxw = int(maxw)
    plan = json.load(open(spec_path))
    tiles = []
    for e in plan:
        im, _ = img(e["item"], e["ev"])
        W, H = im.size
        x0, y0, x1, y1 = e["box"]
        c = im.crop((int(x0*W), int(y0*H), int(x1*W), int(y1*H)))
        if c.size[0] < 2 or c.size[1] < 2:
            continue
        sc = scale
        if c.size[0]*sc > maxw:
            sc = maxw / c.size[0]
        c = c.resize((max(1,int(c.size[0]*sc)), max(1,int(c.size[1]*sc))), Image.LANCZOS)
        tiles.append((e, c))
    if not tiles:
        print("nothing to verify"); return
    labh = 13
    Wt = max(t[1].size[0] for t in tiles) + 8
    Ht = sum(t[1].size[1] + labh + 8 for t in tiles) + 8
    sheet = Image.new("RGB", (Wt, Ht), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    yy = 4
    for e, c in tiles:
        d.text((4, yy), f"[{e['ev']}] {e.get('title','')[:110]}", fill=(180, 0, 0))
        yy += labh
        sheet.paste(c, (4, yy))
        d.rectangle([3, yy-1, 4+c.size[0], yy+c.size[1]], outline=(0, 140, 0))
        yy += c.size[1] + 8
    out = f"{TMP}/{name}.png"
    sheet.save(out)
    print(out, sheet.size, f"{len(tiles)} boxes")


def cmd_proof(spec_path, iid, evid, name=None):
    """Draw planned boxes onto the full page so placement can be eyeballed in one Read."""
    plan = [e for e in json.load(open(spec_path)) if e["item"] == iid and e["ev"] == evid]
    im, _ = img(iid, evid)
    W, H = im.size
    d = ImageDraw.Draw(im)
    for i, e in enumerate(plan):
        x0, y0, x1, y1 = e["box"]
        d.rectangle([x0*W, y0*H, x1*W, y1*H], outline=(255, 0, 0), width=2)
        d.text((x0*W + 2, max(0, y0*H - 11)), str(i), fill=(255, 0, 0))
    sc = min(1.0, 1500 / max(W, H))
    if sc < 1.0:
        im = im.resize((int(W*sc), int(H*sc)), Image.LANCZOS)
    out = f"{TMP}/{name or (iid+'_'+evid+'_proof')}.png"
    im.save(out)
    print(out, im.size, f"{len(plan)} boxes")


def cmd_resolve(plan_path, out_path):
    """plan entries: {item, ev, key, title, det:[x0,x1,y0,y1], lines:"12" | "12-13",
       bx:[x0,x1] (optional wider box window), box:[..] (explicit, skips detection)}"""
    plan = json.load(open(plan_path))
    cache = {}
    out = []
    for e in plan:
        if "box" in e:
            out.append(e); continue
        mode = e.get("mode", "profile")
        k = (e["item"], e["ev"], tuple(e["det"]), mode, e.get("minsep", 0.55))
        if k not in cache:
            dx0, dx1, dy0, dy1 = e["det"]
            if mode == "valley":
                cache[k] = detect_lines_valley(e["item"], e["ev"], dx0, dx1, dy0, dy1,
                                               minsep=e.get("minsep", 0.55))[0]
            else:
                cache[k] = detect_lines(e["item"], e["ev"], dx0, dx1, dy0, dy1)[0]
        bands = cache[k]
        spec = str(e["lines"])
        if "-" in spec:
            p, q = spec.split("-"); lo, hi = bands[int(p)][0], bands[int(q)][1]
        else:
            lo, hi = bands[int(spec)]
        bx0, bx1 = e.get("bx", [e["det"][0], e["det"][1]])
        tb = tight_box(e["item"], e["ev"], lo, hi, bx0, bx1)
        if tb is None:
            e["box"] = [bx0, round(lo, 4), bx1, round(hi, 4)]; e["_noink"] = True
        else:
            e["box"] = [round(v, 4) for v in tb]
        out.append(e)
    json.dump(out, open(out_path, "w"), indent=1)
    for e in out:
        b = e["box"]
        print(f'{e["item"]} {e["ev"]} {e.get("key","")}  x={b[0]:.3f} y={b[1]:.3f} w={b[2]-b[0]:.3f} h={b[3]-b[1]:.3f}  | {e.get("title","")[:60]}')


def cmd_headers(spec_path, name="headers", y0=0.0, y1=0.15, w=560):
    """spec: [[item,ev],...] -> one stacked sheet of page-top bands, for right-page screening."""
    y0, y1, w = float(y0), float(y1), int(w)
    pairs = json.load(open(spec_path))
    tiles = []
    for iid, evid in pairs:
        im, _ = img(iid, evid)
        W, H = im.size
        c = im.crop((0, int(y0*H), W, int(y1*H)))
        sc = w / c.size[0]
        c = c.resize((w, max(1, int(c.size[1]*sc))), Image.LANCZOS)
        tiles.append((iid, evid, c))
    labh = 12
    sheet = Image.new("RGB", (w + 8, sum(t[2].size[1] + labh + 6 for t in tiles) + 8), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    yy = 4
    for iid, evid, c in tiles:
        d.text((4, yy), f"{iid} {evid}", fill=(180, 0, 0))
        yy += labh
        sheet.paste(c, (4, yy))
        yy += c.size[1] + 6
    out = f"{TMP}/{name}.png"
    sheet.save(out)
    print(out, sheet.size, f"{len(tiles)} pages")


def detect_lines_valley(iid, evid, x0=0.0, x1=1.0, y0=0.0, y1=1.0, upscale=3, smooth=2, minsep=0.55):
    """For tight leading / low-DPI scans: upsample, smooth the ink profile, cut at valleys."""
    im, _ = img(iid, evid)
    W, H = im.size
    a, b = int(y0*H), int(y1*H)
    c0, c1 = int(x0*W), int(x1*W)
    sub = im.crop((c0, a, c1, b))
    up = sub.resize((sub.size[0]*upscale, sub.size[1]*upscale), Image.LANCZOS).convert("L")
    g = np.asarray(up, dtype=np.float32)
    bg = np.median(g)
    ink = (g < bg - 28).astype(np.float32)
    prof = ink.mean(axis=1)
    k = max(1, int(smooth*upscale))
    ker = np.ones(k)/k
    sm = np.convolve(prof, ker, mode="same")
    # dominant line pitch via autocorrelation
    p = sm - sm.mean()
    ac = np.correlate(p, p, mode="full")[len(p)-1:]
    lo = max(3, int(4*upscale))
    hi = min(len(ac)-1, int(60*upscale))
    pitch = lo + int(np.argmax(ac[lo:hi])) if hi > lo else int(10*upscale)
    # cut at local minima at least minsep*pitch apart
    cuts = []
    win = max(2, int(minsep*pitch))
    i = win
    while i < len(sm)-win:
        seg = sm[i-win:i+win+1]
        if sm[i] == seg.min() and (not cuts or i - cuts[-1] >= win):
            cuts.append(i)
        i += 1
    edges = [0] + cuts + [len(sm)]
    bands = []
    for u, v in zip(edges[:-1], edges[1:]):
        seg = ink[u:v]
        rows = np.where(seg.sum(axis=1) > 0)[0]
        if len(rows) == 0:
            continue
        ra, rb = u+rows[0], u+rows[-1]
        if rb - ra < 2:
            continue
        bands.append(((a + ra/upscale)/H, (a + rb/upscale + 1)/H))
    return bands, (W, H), pitch/upscale


def cmd_sheetv(iid, evid, x0, x1, y0, y1, scale=2.0, name=None, minsep=0.55):
    x0, x1, y0, y1, scale, minsep = float(x0), float(x1), float(y0), float(y1), float(scale), float(minsep)
    bands, (W, H), pitch = detect_lines_valley(iid, evid, x0, x1, y0, y1, minsep=minsep)
    im, _ = img(iid, evid)
    tiles = []
    for k, (p, q) in enumerate(bands):
        c = im.crop((int(x0*W), int(p*H), int(x1*W), int(q*H)))
        if c.size[1] < 2:
            continue
        tiles.append((k, c.resize((int(c.size[0]*scale), max(1, int(c.size[1]*scale))), Image.LANCZOS), p, q))
    if not tiles:
        print("no lines"); return
    labw = 46
    Wt = max(t[1].size[0] for t in tiles) + labw + 6
    sheet = Image.new("RGB", (Wt, sum(t[1].size[1]+6 for t in tiles)+8), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    yy = 4
    for k, c, p, q in tiles:
        sheet.paste(c, (labw, yy))
        d.text((4, yy + max(0, c.size[1]//2 - 5)), f"L{k:02d}", fill=(200, 0, 0))
        d.line([(0, yy+c.size[1]+3), (Wt-2, yy+c.size[1]+3)], fill=(225, 225, 225))
        yy += c.size[1] + 6
    out = f"{TMP}/{name or (iid+'_'+evid+'_sheetv')}.png"
    sheet.save(out)
    print(out, sheet.size, f"{len(tiles)} lines  pitch~{pitch:.1f}px")
    for k, c, p, q in tiles:
        print(f"  L{k:02d} y={p:.4f}..{q:.4f}")
