#!/usr/bin/env python3
"""Carry reviewer adjudications from dataset v4 onto dataset v5.

v5 consolidates per-book `date` claims into one event-level `date` claim and retires
per-book `evidence_verb` claims. This script rewrites an exported results file so no
already-made decision has to be redone:

  * decided per-book dates -> the item's `_event:date` result, when they agree;
  * stale `evidence_verb` (and consolidated `date`) result keys pruned;
  * everything else passes through untouched, keyed by the same stable item/section ids.

Input is the app's "Export JSON" backup, or its "Export CSV" when that is all we have.
The output re-imports through Settings -> Import adjudications (JSON), which merges by item.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

EVENT_DATE_KEY = "_event:date"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--results", type=Path, help="app Export JSON backup")
    src.add_argument("--csv", type=Path, help="app Export CSV (fallback when no JSON backup exists)")
    p.add_argument("--dataset", type=Path, required=True, help="dataset.v5.json")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    return p.parse_args()


def results_from_json(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("results", data)


def results_from_csv(path: Path) -> dict[str, dict[str, Any]]:
    """Reconstruct the JSON backup shape from the per-claim CSV export."""
    out: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            item_id = row["item_id"]
            r = out.setdefault(item_id, {"itemId": item_id, "fields": {}, "addedTitles": [], "status": row["item_status"], "updatedAt": 0})
            if row.get("evidence_insufficient") == "TRUE":
                r["insufficient"] = True
            if row.get("notes"):
                r["notes"] = row["notes"]
            if row.get("record_origin") == "reviewer_added" and row.get("field") == "title_as_printed":
                r["addedTitles"].append({"id": row["section"], "value": row["value"], "evidenceId": row.get("evidence_id") or None})
                continue
            if row.get("field") == "date_override" and row.get("value"):
                r.setdefault("dateOverrides", []).append({"sectionKey": row["section"], "value": row["value"]})
                continue
            if not row.get("choice"):
                continue
            fr: dict[str, Any] = {"choice": row["choice"], "value": row["value"] or None}
            if row.get("custom_text"):
                fr["custom"] = row["custom_text"]
            r["fields"][f"{row['section']}:{row['field']}"] = fr
    for r in out.values():
        if not r["addedTitles"]:
            del r["addedTitles"]
    return out


def dataset_shapes(dataset: dict[str, Any]) -> tuple[set[str], dict[str, bool], dict[str, set[str]]]:
    """item ids; item has event-level date; per-item sections that STILL carry a date field."""
    ids: set[str] = set()
    has_event_date: dict[str, bool] = {}
    dated_sections: dict[str, set[str]] = {}
    for item in dataset["items"]:
        ids.add(item["id"])
        has_event_date[item["id"]] = any(f.get("key") == "date" for f in item.get("eventFields", []))
        dated_sections[item["id"]] = {
            b["key"] for b in item.get("books", []) if any(f.get("key") == "date" for f in b.get("fields", []))
        }
    return ids, has_event_date, dated_sections


def decided(fr: dict[str, Any] | None) -> bool:
    if not fr or not fr.get("choice"):
        return False
    if fr["choice"] == "custom":
        return bool((fr.get("value") or "").strip() or (fr.get("custom") or "").strip())
    return True


def main() -> None:
    args = parse_args()
    results = results_from_json(args.results) if args.results else results_from_csv(args.csv)
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    ids, has_event_date, dated_sections = dataset_shapes(dataset)

    report: dict[str, Any] = {
        "input_items_with_results": 0, "event_dates_migrated": 0,
        "event_dates_conflicting_left_unset": [], "verb_keys_pruned": 0,
        "date_keys_pruned": 0, "results_for_items_no_longer_in_dataset": [],
    }
    date_key = re.compile(r"^(?P<section>.+):date$")

    for item_id, r in results.items():
        fields: dict[str, Any] = r.get("fields") or {}
        if not fields and not r.get("addedTitles") and not r.get("insufficient") and not r.get("notes"):
            continue
        report["input_items_with_results"] += 1
        if item_id not in ids:
            # deliberately RETAINED in the output: the reviewer's work on since-dropped
            # items is preserved as an inert record (harmless orphan in IndexedDB)
            report["results_for_items_no_longer_in_dataset"].append(item_id)
            continue

        # 1. decided per-book dates -> event date (when the item was consolidated and they agree)
        if has_event_date.get(item_id) and not decided(fields.get(EVENT_DATE_KEY)):
            decided_dates = [
                (key, fr) for key, fr in fields.items()
                if (m := date_key.match(key)) and m.group("section") != "_event" and decided(fr)
            ]
            if decided_dates:
                # agreement is on the RESOLVED date, not on provenance: picking the same
                # date off the Claude pill on one book and the Codex pill on another is
                # agreement, not conflict (not_stated / cant_tell stay distinct outcomes)
                def signature(fr: dict[str, Any]) -> tuple[str, str]:
                    if fr.get("choice") in ("not_stated", "cant_tell"):
                        return (fr["choice"], "")
                    return ("value", (fr.get("value") or fr.get("custom") or "").strip())

                signatures = {signature(fr) for _, fr in decided_dates}
                if len(signatures) == 1:
                    choices = {fr.get("choice") for _, fr in decided_dates}
                    first = dict(decided_dates[0][1])
                    if len(choices) > 1 and signature(first)[0] == "value":
                        value = signature(first)[1]
                        first = {"choice": "custom", "value": value, "custom": value}
                    fields[EVENT_DATE_KEY] = first
                    report["event_dates_migrated"] += 1
                else:
                    report["event_dates_conflicting_left_unset"].append(item_id)

        # 2. prune retired keys
        for key in list(fields):
            section, _, field = key.rpartition(":")
            if field == "evidence_verb":
                del fields[key]
                report["verb_keys_pruned"] += 1
            elif field == "date" and section != "_event" and section not in dated_sections.get(item_id, set()):
                del fields[key]
                report["date_keys_pruned"] += 1
        r["fields"] = fields

    out = {
        "datasetName": dataset["meta"]["name"],
        "schema": 2,
        "migratedFor": "dataset schema 7 (v5)",
        "nResults": len(results),
        "results": results,
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["event_dates_conflicting_left_unset"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
