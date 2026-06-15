#!/usr/bin/env python3
"""
prewarm_ocr.py — parallel OCR + WebP encode so build_dataset.py becomes fast assembly.

Parallelism uses INDEPENDENT SUBPROCESSES (one RapidOCR engine each) rather than
multiprocessing.Pool, which deadlocks with onnxruntime on Windows. Each worker OCRs a
deterministic shard of the work into .shard_*.json; the launcher merges shards into
.ocr_cache.json. Reuses build_dataset's crop logic so crop ids/keys match.

  python tools/prewarm_ocr.py            # launch (encode + sharded OCR + crops)
  python tools/prewarm_ocr.py --of 8 --threads 2
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B  # noqa: E402

CROP_JOBS = B.HERE / ".crop_jobs.json"


def targets():
    snippets, fulls, strips, nosnip = set(), set(), set(), []
    for year in B.YEARS:
        man = B.load_csv(B.PANELS / f"manifest_{year}.csv")
        for _, row in man.items():
            n = B.num_or_none(row.get("n") or row.get("inst_number"))
            def g(c):
                v = row.get(c, "")
                return v.strip() if v and v.strip().lower() != "nan" else None
            if year == 1953:
                if g("snippet"): snippets.add(g("snippet"))
                if g("full"): fulls.add(g("full"))
            elif year in (1956, 1959, 1962, 1965):
                for c in ("L_snippet", "R_snippet"):
                    if g(c): snippets.add(g(c))
                for c in ("L_full", "R_full"):
                    if g(c): fulls.add(g(c))
            elif year == 1939:
                pn, pr = g("names_image"), g("resources_image")
                for p in (pn, pr):
                    if p: fulls.add(p)
                if pr and n is not None: strips.add(pr); nosnip.append((pr, n))
            elif year in (1947, 1950):
                pg, pr = g("gs_image"), g("res_image")
                for p in (pg, pr):
                    if p: fulls.add(p)
                if pr and n is not None: strips.add(pr); nosnip.append((pr, n))
                if pg and n is not None: strips.add(pg); nosnip.append((pg, n))
    ex = os.path.exists
    return (sorted(p for p in snippets if ex(p)), sorted(p for p in fulls if ex(p)),
            sorted(p for p in strips if ex(p)), nosnip)


def _toks(res):
    out = []
    for box, txt, score in (res or []):
        xs = [float(p[0]) for p in box]; ys = [float(p[1]) for p in box]
        out.append({"t": str(txt), "x0": min(xs), "y0": min(ys),
                    "x1": max(xs), "y1": max(ys), "s": float(score)})
    return out


def _engine(threads):
    os.environ.setdefault("OMP_NUM_THREADS", str(threads))
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=threads)


def run_worker(kind, shard, of, threads):
    from PIL import Image
    import numpy as np
    cache = B.load_ocr_cache()
    eng = _engine(threads)
    out, sp = {}, B.HERE / f".shard_{kind}_{shard}.json"

    def flush():
        sp.write_text(json.dumps(out))

    snippets, _, strips, _ = targets()
    if kind == "snippets":
        items = [p for p in snippets[shard::of] if p not in cache]
        for i, p in enumerate(items, 1):
            W, H = Image.open(p).size
            out[p] = {"w": W, "h": H, "tokens": _toks(eng(p)[0])}
            if i % 5 == 0: flush(); print(f"{kind}#{shard}: {len(out)} done", flush=True)
    elif kind == "strips":
        items = [p for p in strips[shard::of] if ("leftcol:" + p) not in cache]
        for i, p in enumerate(items, 1):
            full = Image.open(p); W, H = full.size
            strip = full.convert("RGB").crop((0, 0, int(W * 0.16), H)); sw, sh = strip.size
            out["leftcol:" + p] = {"w": sw, "h": sh, "tokens": _toks(eng(np.array(strip))[0])}
            if i % 5 == 0: flush(); print(f"{kind}#{shard}: {len(out)} done", flush=True)
    elif kind == "crops":
        jobs = json.loads(CROP_JOBS.read_text())[shard::of]
        for i, (page, y0, y1, cid) in enumerate(jobs, 1):
            im = Image.open(page).convert("RGB"); W, _ = im.size
            crop = im.crop((0, y0, W, y1)); cw, ch = crop.size
            fp = B.DEFAULT_OUT / "images" / f"{cid}.webp"
            if not fp.exists():
                o = crop
                if cw > B.SNIP_MAXW:
                    s = B.SNIP_MAXW / cw; o = crop.resize((round(cw * s), round(ch * s)), Image.LANCZOS)
                o.save(fp, "WEBP", quality=B.SNIP_Q, method=4)
            out["crop:" + cid] = {"w": cw, "h": ch, "tokens": _toks(eng(np.array(crop))[0])}
            if i % 5 == 0: flush(); print(f"{kind}#{shard}: {len(out)} done", flush=True)
    flush()
    print(f"shard {kind}#{shard} done: {len(out)}")


def encode_all():
    from PIL import Image
    snippets, fulls, _, _ = targets()
    jobs = [(p, "snippet") for p in snippets] + [(p, "full") for p in fulls]
    made = 0
    for src, role in jobs:
        fp = B.DEFAULT_OUT / "images" / f"{B.short_id(src)}.webp"
        if fp.exists():
            continue
        im = Image.open(src).convert("RGB"); w, h = im.size
        mx = B.SNIP_MAXW if role == "snippet" else B.FULL_MAXSIDE
        if max(w, h) > mx:
            s = mx / max(w, h); im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
        fp.parent.mkdir(parents=True, exist_ok=True)
        im.save(fp, "WEBP", quality=B.SNIP_Q if role == "snippet" else B.FULL_Q, method=4)
        made += 1
    print(f"encode: {made} new (of {len(jobs)})")


def merge(kind, of):
    cache = B.load_ocr_cache()
    n = 0
    for k in range(of):
        sp = B.HERE / f".shard_{kind}_{k}.json"
        if sp.exists():
            d = json.loads(sp.read_text()); cache.update(d); n += len(d); sp.unlink()
    B.save_ocr_cache()
    print(f"merged {kind}: +{n} (cache now {len(cache)})")


def spawn(kind, of, threads, stagger=10):
    # Stagger startup: concurrent onnxruntime init contends badly on Windows and can deadlock.
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    procs = []
    for k in range(of):
        procs.append(subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()),
                                       "--worker", kind, "--shard", str(k), "--of", str(of),
                                       "--threads", str(threads)], env=env))
        if k < of - 1:
            time.sleep(stagger)
    for p in procs:
        p.wait()


def launch(of, threads, stagger):
    t0 = time.time()
    print("[encode]"); encode_all()
    print(f"[OCR snippets] {of} workers x {threads} threads"); spawn("snippets", of, threads, stagger); merge("snippets", of)
    print("[OCR strips]"); spawn("strips", of, threads, stagger); merge("strips", of)
    print("[crop windows]")
    cache = B.load_ocr_cache()
    jobs, seen = [], set()
    _, _, _, nosnip = targets()
    for page, n in nosnip:
        win = B.row_crop_window(page, n)
        if not win:
            continue
        y0, y1 = win[0], win[1]
        cid = "crop_" + B.short_id(page, n, y0, y1)
        if cid in seen:
            continue
        seen.add(cid)
        if ("crop:" + cid) in cache and (B.DEFAULT_OUT / "images" / f"{cid}.webp").exists():
            continue
        jobs.append([page, y0, y1, cid])
    CROP_JOBS.write_text(json.dumps(jobs))
    print(f"    {len(jobs)} crops to make (of {len(seen)} rows located, {len(nosnip)} attempts)")
    if jobs:
        spawn("crops", of, threads, stagger); merge("crops", of)
    print(f"PREWARM DONE in {time.time()-t0:.0f}s — now run build_dataset.py --zip")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", choices=["snippets", "strips", "crops"])
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--of", type=int, default=10)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--stagger", type=float, default=7)
    a = ap.parse_args()
    if a.worker:
        run_worker(a.worker, a.shard, a.of, a.threads)
    else:
        launch(a.of, a.threads, a.stagger)


if __name__ == "__main__":
    main()
