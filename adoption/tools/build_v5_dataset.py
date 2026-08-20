#!/usr/bin/env python3
"""Reshape the v4 literal-title artifact into dataset v5 (2026-08 review feedback).

In-place transform of the shipped artifact — deliberately NOT a re-run of the upstream
selection, so every item id, groupKey, and book section key survives and existing
reviewer results re-import untouched.

Operations (each optional input simply skipped when absent):
  1. Per-book `evidence_verb` claims -> read-only `verb` metadata on the section.
  2. Per-book `date` claims -> one event-level `date` claim when every book in the
     bundle carries identical date candidates (the divergent bundles keep per-book dates).
  3. Drop non-K12 events (Institute / Deaf / Normal / College / Preparatory, incl.
     teachers' institutes) and the hand-extracted Virginia Table No. 12 items, into a ledger.
  4. `author_as_stated` joined onto book sections from the staging table (record_uid[:8]).
  5. Corrected evidence sourceKind/layout from an audit file (--reclass).
  6. Auto-generated title-anchor regions from one or more --regions files
     (never clobbers refs that already carry hand-drawn regions).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

NON_K12 = re.compile(r"\b(institute|institution|deaf|normal|college|preparatory)\b", re.I)

# Hand extraction (Vitaliia's 115-row transcription of the 1885 Virginia School Report
# Table No. 12) is canonical for these events; they leave the review queue.
VA_TABLE12_HAND_EXTRACTED = {
    "evt_0d8d918da594",  # Manchester City School Board
    "evt_1b4e20af93e9",  # Petersburg City School Board
    "evt_85a26dbb91dc",  # Fredericksburg City School Board
}

EVENT_DATE_HINT = (
    "The whole batch shares this date — confirm it once. "
    "If a single title differs, use “Date differs for this title” under that title."
)

# --- state-history deprioritization (user decision 2026-08-19) ---------------------
# State histories are outside the national analysis core: their title sections become
# OPTIONAL (decidable, never required) — except in bundles that also carry US-history
# titles, where verifying them costs one tap and keeps the event record complete.
STATE_NAMES = (
    "Alabama|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Idaho|"
    "Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|"
    "Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|"
    "New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|"
    "South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|"
    "Wisconsin|Wyoming"
)
US_HISTORY_RE = re.compile(
    r"\b(united states|u\.?\s?s\.?|american|america|our country)\b", re.I)
STATE_HISTORY_RE = re.compile(
    r"(?:\b(?:histor\w*|stories)\b.{0,30}\b(" + STATE_NAMES + r")\b"
    r"|\b(" + STATE_NAMES + r")\b.{0,15}\bhistor\w*\b"
    r"|^[A-Z][\w.&' ]{1,25}[’']s?\s+(" + STATE_NAMES + r")\s*[,.]?$)", re.I)


def is_state_history(title: str) -> bool:
    return bool(STATE_HISTORY_RE.search(title or "")) and not US_HISTORY_RE.search(title or "")


def mark_state_histories_optional(item: dict[str, Any], stats: Counter) -> None:
    books = item.get("books", [])
    has_us_history = any(
        US_HISTORY_RE.search(b.get("title_as_stated") or "") and not b.get("optional")
        for b in books
    )
    if has_us_history:
        return  # bundled with US histories: reviewing the state title costs one tap
    flipped = 0
    for b in books:
        if b.get("optional") or not is_state_history(b.get("title_as_stated") or ""):
            continue
        b["optional"] = True
        b["note"] = ((b.get("note") or "") + " State history — outside the national analysis core; "
                     "optional, does not block completion.").strip()
        flipped += 1
    if flipped:
        stats["state_history_sections_made_optional"] += flipped
        # a bundle left with zero required decisions can never complete — keep one anchor
        required = len(item.get("eventFields") or []) + sum(1 for b in books if not b.get("optional"))
        if required == 0:
            first = next(b for b in books if b.get("optional"))
            first["optional"] = False
            stats["state_history_kept_required_anchor"] += 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True, help="v4 dataset.ground-truth.json")
    p.add_argument("--staging", type=Path, help="staging_records CSV the build drew from (author join)")
    p.add_argument("--reclass", type=Path, help="evidence_reclass.json audit file")
    p.add_argument("--page-fixes", type=Path, help="page_fixes.json: re-rendered correct pages for wrong-page refs")
    p.add_argument("--page-additions", type=Path,
                   help="new evidence refs to append (e.g. a facing page carrying titles the main page lacks)")
    p.add_argument("--alerts", type=Path,
                   help="JSON {itemId: alert} — reviewer warnings discovered by evidence audits")
    p.add_argument("--notes", type=Path,
                   help="JSON {itemId: note} — quiet context appended to item.note (e.g. machine-confirmation provenance)")
    p.add_argument("--add-titles", type=Path,
                   help="JSON {itemId: [{key, title_as_stated, note}]} — new title sections found by re-extraction")
    p.add_argument("--regions", type=Path, action="append", default=[], help="auto-region file(s); repeatable")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--dropped", type=Path, required=True, help="ledger of dropped items")
    return p.parse_args()


def load_author_map(staging: Path | None) -> dict[str, str]:
    """record_uid[:8] -> author_as_stated.

    A prefix shared by more than one full record_uid is dropped outright (even when
    only one of them has an author) — the section key carries only 8 hex chars, so a
    shared prefix cannot be attributed to either record.
    """
    if staging is None:
        return {}
    uids: dict[str, set[str]] = {}
    authors: dict[str, set[str]] = {}
    with staging.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            uid = row.get("record_uid") or ""
            uid8 = uid[:8]
            if not uid8:
                continue
            uids.setdefault(uid8, set()).add(uid)
            author = (row.get("author_as_stated") or "").strip()
            if author:
                authors.setdefault(uid8, set()).add(author)
    return {
        uid8: names.pop()
        for uid8, names in ((k, set(v)) for k, v in authors.items())
        if len(names) == 1 and len(uids.get(uid8, ())) == 1
    }


def section_uid8(section_key: str) -> str | None:
    m = re.fullmatch(r"b\d*_([0-9a-f]{8})x*", section_key)
    return m.group(1) if m else None


def candidate_signature(field: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Source AND value: two books whose candidates carry the same values from
    different sources are NOT the same claim and must not be consolidated."""
    return tuple(sorted((c.get("source", ""), c.get("value", "")) for c in field.get("candidates", [])))


def drop_reason(item: dict[str, Any]) -> str | None:
    if item["id"] in VA_TABLE12_HAND_EXTRACTED:
        return "va_table12_hand_extracted_canonical"
    blob = f"{item.get('title', '')} {item.get('subtitle', '')}"
    m = NON_K12.search(blob)
    if m:
        return f"non_k12_institution ({m.group(0)})"
    return None


def consolidate_dates(item: dict[str, Any], stats: Counter) -> None:
    """Move identical per-book date claims up to one event-level claim."""
    books = item.get("books", [])
    dated = [(b, f) for b in books for f in b.get("fields", []) if f.get("key") == "date"]
    if not dated:
        return
    if len(dated) < len(books):
        # a book without its own date field cannot be asserted to share the others' date
        stats["items_partial_date_coverage_kept_per_book"] += 1
        return
    signatures = {candidate_signature(f) for _, f in dated}
    if len(signatures) > 1:
        stats["items_divergent_dates_kept_per_book"] += 1
        return
    first = dated[0][1]
    evidence_ids: list[str] = []
    for _, f in dated:
        for ev in f.get("evidenceIds", []):
            if ev not in evidence_ids:
                evidence_ids.append(ev)
    values = {c.get("value", "") for c in first.get("candidates", [])}
    event_field = {
        "key": "date",
        "label": "Adoption date",
        "valueType": "text",
        "candidates": first.get("candidates", []),
        "default": first.get("default"),
        "agree": len(values) == 1 and bool(first.get("candidates")),
        "evidenceIds": evidence_ids,
        "flags": [] if len(values) <= 1 else ["conflict"],
        "hint": EVENT_DATE_HINT,
    }
    item.setdefault("eventFields", []).insert(0, event_field)
    for book, field in dated:
        book["fields"].remove(field)
        stats["book_date_fields_removed"] += 1
    stats["event_date_fields_added"] += 1


def extract_verbs(item: dict[str, Any], stats: Counter) -> None:
    for book in item.get("books", []):
        for field in list(book.get("fields", [])):
            if field.get("key") != "evidence_verb":
                continue
            candidate = next(iter(field.get("candidates", [])), None)
            if candidate and candidate.get("value"):
                book["verb"] = {"value": candidate["value"], "source": candidate.get("source", "")}
                stats["verbs_kept_as_metadata"] += 1
            book["fields"].remove(field)
            stats["verb_fields_removed"] += 1


def join_authors(item: dict[str, Any], authors: dict[str, str], stats: Counter) -> None:
    for book in item.get("books", []):
        if book.get("author_as_stated"):
            continue
        uid8 = section_uid8(book.get("key", ""))
        author = authors.get(uid8 or "")
        if author:
            book["author_as_stated"] = author
            stats["authors_joined"] += 1


def apply_reclass(item: dict[str, Any], reclass: dict[str, Any], stats: Counter) -> None:
    per_item = reclass.get("refs", {}).get(item["id"], {})
    for ref in item.get("evidence", []):
        entry = per_item.get(ref.get("id"))
        if not entry:
            continue
        for key in ("sourceKind", "layout"):
            new = entry.get(key)
            if new != ref.get(key):
                stats[f"reclass_{key}_changed"] += 1
            if new is None:
                ref.pop(key, None)
            else:
                ref[key] = new


def apply_page_fixes(item: dict[str, Any], fixes: dict[str, Any], stats: Counter) -> None:
    """Point refs whose scan showed the wrong page at the re-rendered correct asset."""
    per_item = fixes.get(item["id"]) or {}
    for ref in item.get("evidence", []):
        fix = per_item.get(ref.get("id"))
        if not fix:
            continue
        if fix.get("unfixable"):
            stats["page_fix_unfixable"] += 1
            continue
        ref["file"] = fix["file"]
        if fix.get("pdfIndex") is not None:
            ref.setdefault("page", {})["pdfIndex"] = fix["pdfIndex"]
        # the old crop's hand regions described the wrong page — they cannot survive the swap
        ref.pop("regions", None)
        stats["page_fixes_applied"] += 1


def apply_page_additions(item: dict[str, Any], additions: dict[str, Any], stats: Counter) -> None:
    """Append builder-supplied extra evidence refs (facing pages etc.)."""
    per_item = additions.get(item["id"]) or {}
    existing = {e.get("id") for e in item.get("evidence", [])}
    for ev_id, spec in per_item.items():
        if ev_id in existing:
            continue
        item["evidence"].append({"id": ev_id, **spec})
        stats["evidence_refs_added"] += 1


def apply_regions(item: dict[str, Any], region_files: list[dict[str, Any]], stats: Counter) -> None:
    # refs that carried regions in the INPUT dataset keep their hand annotations;
    # regions added by earlier --regions files in THIS run extend, not block, later files
    hand_annotated = {ref.get("id") for ref in item.get("evidence", []) if ref.get("regions")}
    augmented: set[str] = set()
    for regions in region_files:
        per_item = regions.get("items", {}).get(item["id"], {})
        for ref in item.get("evidence", []):
            new_regions = per_item.get(ref.get("id"))
            if not new_regions:
                continue
            cleaned = [
                {k: v for k, v in region.items() if k in ("x", "y", "w", "h", "kind", "label", "fieldKeys")}
                for region in new_regions
                if region.get("confidence") != "low"
            ]
            if not cleaned:
                continue
            # never seen new fieldKeys twice: drop boxes whose anchor already exists on this ref
            existing_keys = {fk for r in (ref.get("regions") or []) for fk in (r.get("fieldKeys") or [])}
            cleaned = [r for r in cleaned if not (r.get("fieldKeys") and set(r["fieldKeys"]) <= existing_keys)]
            if not cleaned:
                stats["regions_skipped_already_anchored"] += 1
                continue
            if ref.get("id") in hand_annotated or ref.get("id") in augmented:
                # hand boxes (and earlier files' boxes) are kept; new anchors append after them
                ref["regions"] = (ref.get("regions") or []) + cleaned
                stats["regions_appended"] += len(cleaned)
            else:
                ref["regions"] = cleaned
                augmented.add(ref.get("id"))
                stats["refs_gaining_regions"] += 1
            stats["regions_added"] += len(cleaned)


def main() -> None:
    args = parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    authors = load_author_map(args.staging)
    reclass = json.loads(args.reclass.read_text(encoding="utf-8")) if args.reclass else None
    page_fixes = json.loads(args.page_fixes.read_text(encoding="utf-8")) if args.page_fixes else None
    page_additions = json.loads(args.page_additions.read_text(encoding="utf-8")) if args.page_additions else None
    alerts = json.loads(args.alerts.read_text(encoding="utf-8")) if args.alerts else {}
    notes = json.loads(args.notes.read_text(encoding="utf-8")) if args.notes else {}
    add_titles = json.loads(args.add_titles.read_text(encoding="utf-8")) if args.add_titles else {}
    region_files = [json.loads(path.read_text(encoding="utf-8")) for path in args.regions]

    stats: Counter = Counter()
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for item in data["items"]:
        reason = drop_reason(item)
        if reason:
            dropped.append({
                "id": item["id"], "groupKey": item.get("groupKey"), "title": item.get("title"),
                "subtitle": item.get("subtitle"), "state": item.get("state"), "year": item.get("year"),
                "group": item.get("group"), "reason": reason,
                "books": [b.get("title_as_stated") for b in item.get("books", [])],
            })
            stats[f"dropped_{'va_table12' if reason.startswith('va_') else 'non_k12'}"] += 1
            continue
        extract_verbs(item, stats)
        consolidate_dates(item, stats)
        join_authors(item, authors, stats)
        if reclass:
            apply_reclass(item, reclass, stats)
        if page_fixes:
            apply_page_fixes(item, page_fixes, stats)
        if page_additions:
            apply_page_additions(item, page_additions, stats)
        if region_files:
            apply_regions(item, region_files, stats)
        if item["id"] in alerts:
            extra = alerts[item["id"]]
            item["alert"] = f"{item['alert']} {extra}".strip() if item.get("alert") else extra
            stats["alerts_added"] += 1
        if item["id"] in notes:
            extra = notes[item["id"]]
            item["note"] = f"{item['note']} {extra}".strip() if item.get("note") else extra
            stats["notes_added"] += 1
        for new_title in add_titles.get(item["id"], []):
            if any(b.get("key") == new_title["key"] for b in item.get("books", [])):
                continue
            item.setdefault("books", []).append({
                "key": new_title["key"],
                "title_as_stated": new_title["title_as_stated"],
                "fields": [],
                "note": new_title.get("note"),
                # re-extraction finds (incl. state histories outside the national analysis core)
                # are decidable but never required — they must not block completion
                "optional": True,
            })
            stats["title_sections_added"] += 1
        mark_state_histories_optional(item, stats)
        kept.append(item)

    meta = data["meta"]
    meta["schema"] = 7
    meta["nItems"] = len(kept)
    meta["states"] = sorted({item["state"] for item in kept})
    meta["years"] = sorted({item["year"] for item in kept})
    meta["note"] = (
        (meta.get("note") or "").rstrip(". ")
        + ". v5 reshape 2026-08: verbs are read-only metadata, one event-level date per bundle "
        "(per-title override in the app), non-K12 events and hand-extracted VA Table No. 12 removed "
        "(see the dropped-items ledger), authors joined, evidence genre re-audited."
    )
    data["items"] = kept

    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    args.dropped.write_text(json.dumps(dropped, ensure_ascii=False, indent=1), encoding="utf-8")
    report = {
        "input_items": len(kept) + len(dropped),
        "output_items": len(kept),
        "dropped_items": len(dropped),
        "stats": dict(sorted(stats.items())),
        "authors_available_in_staging": len(authors),
        "reclass_applied": bool(reclass),
        "region_files_applied": len(region_files),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not kept:
        sys.exit(1)


if __name__ == "__main__":
    main()
