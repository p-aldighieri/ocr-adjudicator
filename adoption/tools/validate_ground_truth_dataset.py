#!/usr/bin/env python3
"""Validate a literal-title adoption review artifact before release."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


TRANSFORM_SYNTAX = re.compile(
    r"\s->\s|parsed from|page uninspected|titles? not printed|\[(?:series phrase|titles? not printed|united states history)",
    re.I,
)
CANONICAL_LEAK = re.compile(
    r"book match|canonical book|internal bridge|authority bridge|matching confidence|"
    r"title/action bridge|(?:exact-)?title bridge|action bridge|no (?:separate )?edition is assigned",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--asset-root", type=Path, required=True, help="directory containing assets/")
    parser.add_argument("--strict-anchors", action="store_true", help="require a region anchor for every title")
    return parser.parse_args()


def add(bucket: list[dict[str, Any]], code: str, **context: Any) -> None:
    bucket.append({"code": code, **context})


def main() -> None:
    args = parse_args()
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    items = data.get("items", [])
    ids = [item.get("id") for item in items]
    if len(ids) != len(set(ids)):
        add(errors, "duplicate_item_id")
    if data.get("meta", {}).get("nItems") != len(items):
        add(errors, "meta_item_count", meta=data.get("meta", {}).get("nItems"), actual=len(items))

    referenced_assets: set[str] = set()
    role_counts: Counter[str] = Counter()
    for item in items:
        item_id = item.get("id")
        evidence = item.get("evidence", [])
        evidence_ids = [entry.get("id") for entry in evidence]
        valid_ids = set(evidence_ids)
        if len(evidence_ids) != len(valid_ids):
            add(errors, "duplicate_evidence_id", item=item_id)
        for entry in evidence:
            role = entry.get("role")
            role_counts[role] += 1
            if role in {"image", "pdf_page"}:
                file_name = entry.get("file")
                if not file_name:
                    add(errors, "visual_without_file", item=item_id, evidence=entry.get("id"))
                elif Path(file_name).is_absolute() or ".." in Path(file_name).parts:
                    add(errors, "unsafe_asset_path", item=item_id, file=file_name)
                elif not (args.asset_root / file_name).is_file():
                    add(errors, "missing_asset", item=item_id, file=file_name)
                else:
                    referenced_assets.add(file_name)
            if "assets disabled" in (entry.get("text") or "").lower():
                add(errors, "assets_disabled_placeholder", item=item_id, evidence=entry.get("id"))
            for region in entry.get("regions", []):
                values = [region.get(key) for key in ("x", "y", "w", "h")]
                if not all(isinstance(value, (int, float)) for value in values):
                    add(errors, "invalid_region_type", item=item_id, evidence=entry.get("id"))
                    continue
                x, y, width, height = values
                if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1.0001 or y + height > 1.0001:
                    add(errors, "invalid_region_bounds", item=item_id, evidence=entry.get("id"), region=region)
            text_fields = " ".join(str(entry.get(key) or "") for key in ("text", "sourceLine"))
            if CANONICAL_LEAK.search(text_fields):
                add(errors, "canonical_leak", item=item_id, evidence=entry.get("id"))

        all_fields = list(item.get("eventFields", []))
        for book in item.get("books", []):
            title = book.get("title_as_stated") or ""
            if TRANSFORM_SYNTAX.search(title):
                add(errors, "nonliteral_title_syntax", item=item_id, book=book.get("key"), title=title)
            if any(field.get("key") == "book_match" for field in book.get("fields", [])):
                add(errors, "book_match_field", item=item_id, book=book.get("key"))
            all_fields.extend(book.get("fields", []))
            anchors = [
                region
                for entry in evidence
                for region in entry.get("regions", [])
                if region.get("kind") in {"passage", "cell"}
            ]
            if not anchors:
                target = errors if args.strict_anchors else warnings
                add(target, "title_without_region_anchor", item=item_id, book=book.get("key"))
        for field in all_fields:
            dangling = [value for value in field.get("evidenceIds", []) if value not in valid_ids]
            if dangling:
                add(errors, "dangling_evidence_id", item=item_id, field=field.get("key"), values=dangling)

        if CANONICAL_LEAK.search(" ".join(str(item.get(key) or "") for key in ("alert", "note"))):
            add(errors, "canonical_leak", item=item_id)

    output = {
        "ok": not errors,
        "counts": {
            "items": len(items),
            "books": sum(len(item.get("books", [])) for item in items),
            "evidence_roles": dict(role_counts),
            "referenced_assets": len(referenced_assets),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
