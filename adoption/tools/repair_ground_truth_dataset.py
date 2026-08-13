#!/usr/bin/env python3
"""Repair an adoption manifest for literal-title ground-truth review.

The newer Aug. 7 manifest preserved the desired 424-item selection but replaced most
visual evidence with ``Not shipped: assets disabled`` text. The older release zip contains
many of those rendered pages, but has a different item sample and cannot replace the newer
manifest wholesale. This script keeps the input selection, reuses only exact item/evidence
visual mappings from the older manifest, applies reviewed overrides, and removes downstream
canonical-book matching.

It never guesses canonical identity. Ambiguous/wrong-page assets remain text evidence and are
reported for review instead of silently falling back to page 1.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


MATCH_ALERT = re.compile(r"at least one title has no confident book match;?\s*", re.I)
SOURCE_PATH = re.compile(r"^File:\s*(.+?)\s*$", re.M)
CANONICAL_NOTE = re.compile(
    r"(?:internal|project authority|internal authority|authority) bridge(?:\s+is|:)?[^.;]*(?:[.;]|$)",
    re.I,
)
MATCH_NOTE = re.compile(r"match(?:ing)?(?: method| confidence)?\s*:[^.;]*(?:[.;]|$)", re.I)
SYNTHETIC_BRIDGE_NOTE = re.compile(
    r"[^.\n;]*(?:title/action bridge|(?:exact-)?title bridge|action bridge)[^.\n;]*(?:[.;]|$)",
    re.I,
)
EDITION_ASSIGNMENT_NOTE = re.compile(r"[^.\n;]*no (?:separate )?edition is assigned[^.\n;]*(?:[.;]|$)", re.I)
TRANSFORM_SYNTAX = re.compile(
    r"\s->\s|parsed from|page uninspected|titles? not printed|\[(?:series phrase|titles? not printed|united states history)",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="newer authoritative dataset.json")
    parser.add_argument("--old-zip", type=Path, help="older visual release zip")
    parser.add_argument("--asset-root", type=Path, required=True, help="directory containing assets/")
    parser.add_argument("--overrides", type=Path, default=Path(__file__).with_name("ground_truth_overrides.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_old_manifest(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith("dataset.json")]
        if len(names) != 1:
            raise SystemExit(f"expected one dataset.json in {path}, found {len(names)}")
        return json.loads(archive.read(names[0]))


def source_path(evidence: dict[str, Any]) -> str | None:
    if evidence.get("sourcePath"):
        return str(evidence["sourcePath"])
    text = evidence.get("text") or ""
    match = SOURCE_PATH.search(text)
    return match.group(1).strip() if match else None


def normalized_source_name(value: str | None) -> str:
    if not value:
        return ""
    stem = Path(value).stem.lower()
    return re.sub(r"[^a-z0-9]+", "", stem)


def compatible_source(current: dict[str, Any], old: dict[str, Any]) -> bool:
    current_name = normalized_source_name(source_path(current))
    old_name = normalized_source_name(old.get("sourcePath") or old.get("sourceLine") or old.get("file"))
    if not current_name or not old_name:
        return current.get("id") == old.get("id")
    return current_name in old_name or old_name in current_name


def unsafe_page_one_fallback(current: dict[str, Any], old: dict[str, Any]) -> bool:
    file_name = Path(old.get("file") or "").name.lower()
    if not re.search(r"(?:^|_)p0*1(?:_|\.)", file_name):
        return False
    citation = " ".join(str(current.get(key) or "") for key in ("label", "sourceLine", "text"))
    roman_page = re.search(r"\b(?:p(?:age)?\.?\s*)?[ivxlcdm]{2,}\b", citation, re.I)
    explicitly_first = re.search(r"\b(?:title page|p(?:age)?\.?\s*1)\b", citation, re.I)
    return bool(roman_page and not explicitly_first)


def classify_source(path: str | None) -> str:
    value = (path or "").lower()
    if (
        re.search(r"(?:american[-_ ]?)?school[-_ ]board[-_ ]journal", value)
        or "/periodicals/" in value
        or "/journals/" in value
        or "magazine" in value
    ):
        return "periodical"
    if "newspaper" in value or re.search(r"(?:gazette|times|herald|tribune|journal|record|news|press)", Path(value).name):
        return "newspaper"
    if "minute" in value or "board" in value:
        return "minutes"
    if "statute" in value or "law" in value:
        return "statute"
    if any(token in value for token in ("report", "superintendent", "departmentofpubl", "annualreport")):
        return "official_report"
    if any(token in value for token in ("periodical", "journal", "magazine")):
        return "periodical"
    return "other"


def scrub_matching_text(value: str | None) -> str | None:
    if not value:
        return value
    value = CANONICAL_NOTE.sub("", value)
    value = MATCH_NOTE.sub("", value)
    value = SYNTHETIC_BRIDGE_NOTE.sub("", value)
    value = EDITION_ASSIGNMENT_NOTE.sub("", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return value or None


def scrub_item(item: dict[str, Any]) -> None:
    alert = MATCH_ALERT.sub("", item.get("alert") or "")
    alert = re.sub(r"Read the evidence before choosing:\s*(?=\.|$)", "", alert, flags=re.I)
    alert = re.sub(r"\s+\.", ".", alert).strip(" ;.")
    if alert:
        item["alert"] = alert
    else:
        item.pop("alert", None)

    item["note"] = scrub_matching_text(item.get("note"))
    if not item.get("note"):
        item.pop("note", None)
    for evidence in item.get("evidence", []):
        path = source_path(evidence)
        if path:
            evidence["sourcePath"] = path
        source_signal = " ".join(
            str(evidence.get(key) or "") for key in ("sourcePath", "sourceLine", "file")
        )
        classified = classify_source(source_signal)
        if evidence.get("sourceKind") is None or classified == "periodical":
            evidence["sourceKind"] = classified
        evidence["sourceLine"] = scrub_matching_text(evidence.get("sourceLine"))
        if not evidence.get("sourceLine"):
            evidence.pop("sourceLine", None)
        evidence["text"] = scrub_matching_text(evidence.get("text"))
        if not evidence.get("text"):
            evidence.pop("text", None)
    for book in item.get("books", []):
        book["fields"] = [field for field in book.get("fields", []) if field.get("key") != "book_match"]
        book["note"] = scrub_matching_text(book.get("note"))
        if not book.get("note"):
            book.pop("note", None)


def relink_from_old(
    item: dict[str, Any],
    old_item: dict[str, Any] | None,
    asset_root: Path,
    report: dict[str, Any],
    blocked_evidence_ids: set[str],
) -> None:
    if not old_item:
        return
    old_evidence = {evidence.get("id"): evidence for evidence in old_item.get("evidence", [])}
    for evidence in item.get("evidence", []):
        if evidence.get("id") in blocked_evidence_ids:
            report["blocked_by_override"].append([item["id"], evidence.get("id")])
            continue
        if evidence.get("role") != "text" or "assets disabled" not in (evidence.get("text") or "").lower():
            continue
        candidate = old_evidence.get(evidence.get("id"))
        if not candidate or candidate.get("role") not in {"image", "pdf_page"}:
            continue
        if not compatible_source(evidence, candidate):
            report["source_mismatch"].append([item["id"], evidence.get("id")])
            continue
        if unsafe_page_one_fallback(evidence, candidate):
            report["blocked_page_one_fallback"].append([item["id"], evidence.get("id"), candidate.get("file")])
            continue
        file_name = candidate.get("file")
        if not file_name or not (asset_root / file_name).is_file():
            report["missing_candidate_asset"].append([item["id"], evidence.get("id"), file_name])
            continue
        preserved = {key: evidence.get(key) for key in ("id", "href") if evidence.get(key) is not None}
        evidence.clear()
        evidence.update(copy.deepcopy(candidate))
        evidence.update(preserved)
        path = source_path(evidence)
        if path:
            evidence["sourcePath"] = path
        evidence.setdefault("sourceKind", classify_source(path or candidate.get("sourceLine")))
        evidence.setdefault("layout", "prose")
        report["relinked"].append([item["id"], evidence.get("id"), file_name])


def replacement_books(item: dict[str, Any], titles: list[str]) -> list[dict[str, Any]]:
    originals = item.get("books", [])
    template = copy.deepcopy(originals[0]) if originals else {"key": "title", "fields": []}
    books = []
    for index, title in enumerate(titles):
        book = copy.deepcopy(originals[index]) if index < len(originals) else copy.deepcopy(template)
        book["key"] = (book.get("key") if index < len(originals) else None) or f"literal_title_{index + 1}"
        book["title_as_stated"] = title
        book["fields"] = [field for field in book.get("fields", []) if field.get("key") != "book_match"]
        books.append(book)
    return books


def apply_overrides(item: dict[str, Any], override: dict[str, Any], report: dict[str, Any]) -> None:
    if "replace_books" in override:
        item["books"] = copy.deepcopy(override["replace_books"])
    if "replace_title_values" in override:
        item["books"] = replacement_books(item, override["replace_title_values"])
    if override.get("note"):
        item["note"] = override["note"]
    for key in ("stateAdoptionRegimeAtEvent", "stateAdoptionCutoff"):
        if key in override:
            item[key] = override[key]

    blocked_paths = [value.lower() for value in override.get("drop_evidence_paths_containing", [])]
    if blocked_paths:
        kept = []
        for evidence in item.get("evidence", []):
            haystack = " ".join(str(evidence.get(key) or "") for key in ("sourcePath", "sourceLine", "text", "file")).lower()
            if any(value in haystack for value in blocked_paths):
                report["dropped_evidence"].append([item["id"], evidence.get("id")])
            else:
                kept.append(evidence)
        item["evidence"] = kept

    by_id = {evidence.get("id"): evidence for evidence in item.get("evidence", [])}
    for evidence_id, replacement in override.get("replace_evidence", {}).items():
        evidence = by_id.get(evidence_id)
        if not evidence:
            evidence = {"id": evidence_id, "sourceLine": replacement.get("label", evidence_id)}
            item.setdefault("evidence", []).append(evidence)
        evidence.update(copy.deepcopy(replacement))
        if replacement.get("role") in {"image", "pdf_page"} and "text" not in replacement:
            evidence.pop("text", None)
        if replacement.get("role") in {"text", "url"} and "file" not in replacement:
            for key in ("file", "page", "regions", "layout"):
                evidence.pop(key, None)
        if replacement.get("role") == "text" and "href" not in replacement:
            evidence.pop("href", None)
        report["overridden_evidence"].append([item["id"], evidence_id, evidence.get("file")])


def remove_dangling_evidence_ids(item: dict[str, Any]) -> None:
    valid = {evidence.get("id") for evidence in item.get("evidence", [])}
    for field in item.get("eventFields", []):
        field["evidenceIds"] = [value for value in field.get("evidenceIds", []) if value in valid]
    for book in item.get("books", []):
        for field in book.get("fields", []):
            field["evidenceIds"] = [value for value in field.get("evidenceIds", []) if value in valid]


def main() -> None:
    args = parse_args()
    dataset = load_json(args.input)
    old = load_old_manifest(args.old_zip)
    overrides = load_json(args.overrides)
    old_items = {item["id"]: item for item in (old or {}).get("items", [])}
    reviewed = overrides.get("items", {})
    report: dict[str, Any] = {
        "relinked": [],
        "overridden_evidence": [],
        "dropped_evidence": [],
        "blocked_page_one_fallback": [],
        "blocked_by_override": [],
        "source_mismatch": [],
        "missing_candidate_asset": [],
        "remaining_assets_disabled": [],
        "quarantined_title_syntax": [],
    }

    for item in dataset.get("items", []):
        scrub_item(item)
        override = reviewed.get(item["id"], {})
        relink_from_old(
            item,
            old_items.get(item["id"]),
            args.asset_root,
            report,
            set(override.get("block_visual_relinks", [])),
        )
        if override:
            apply_overrides(item, override, report)
        # Relinked and override evidence can reintroduce legacy provenance strings, so apply the
        # same ground-truth boundary after those mutations as well as before them.
        scrub_item(item)
        remove_dangling_evidence_ids(item)
        for evidence in item.get("evidence", []):
            if "assets disabled" in (evidence.get("text") or "").lower():
                report["remaining_assets_disabled"].append([item["id"], evidence.get("id"), source_path(evidence)])
        for book in item.get("books", []):
            if TRANSFORM_SYNTAX.search(book.get("title_as_stated") or ""):
                report["quarantined_title_syntax"].append([item["id"], book.get("key"), book.get("title_as_stated")])

    dataset.setdefault("meta", {})["schema"] = max(4, int(dataset.get("meta", {}).get("schema", 0)) + 1)
    dataset["meta"]["note"] = "Literal printed-title ground-truth artifact; canonical-book matching is downstream and intentionally absent."
    dataset["meta"]["nItems"] = len(dataset.get("items", []))
    report["counts"] = {
        "items": len(dataset.get("items", [])),
        "books": sum(len(item.get("books", [])) for item in dataset.get("items", [])),
        "evidence_roles": Counter(
            evidence.get("role") for item in dataset.get("items", []) for evidence in item.get("evidence", [])
        ),
    }
    report["counts"]["evidence_roles"] = dict(report["counts"]["evidence_roles"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    print(f"relinked={len(report['relinked'])}; remaining_disabled={len(report['remaining_assets_disabled'])}")


if __name__ == "__main__":
    main()
