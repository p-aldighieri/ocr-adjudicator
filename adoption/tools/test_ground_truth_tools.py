from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from repair_ground_truth_dataset import classify_source


TOOLS = Path(__file__).resolve().parent


class GroundTruthToolsTest(unittest.TestCase):
    def test_school_board_journal_is_a_periodical_not_a_newspaper(self) -> None:
        self.assertEqual(
            classify_source("journals/asbj/sim_american-school-board-journal_1898-02.pdf"),
            "periodical",
        )
        self.assertEqual(classify_source("newspapers/journal_courier_1896.jpg"), "newspaper")

    def test_repair_relinks_visual_and_removes_matching(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "assets").mkdir()
            asset = "assets/hash_p0002_paper.jpg"
            (root / asset).write_bytes(b"test image placeholder")
            current = {
                "meta": {"name": "test", "schema": 3, "nItems": 1, "states": ["AR"], "years": [1898], "sources": []},
                "items": [{
                    "id": "evt1", "groupKey": "AR|test|1898", "group": "conflicts",
                    "title": "Test", "subtitle": "Arkansas", "state": "AR", "year": 1898, "priority": 0.5,
                    "note": "The title/action bridge remains composite and no edition is assigned.",
                    "alert": "Read the evidence before choosing: at least one title has no confident book match.",
                    "evidence": [{
                        "id": "ev1", "role": "text", "label": "Citation p. 2", "sourceLine": "Paper p. 2",
                        "text": "File: sources/newspapers/paper.pdf\nNot shipped: assets disabled.\nInternal bridge is Some Canonical Book."
                    }],
                    "books": [{
                        "key": "b1", "title_as_stated": "Title As Printed", "fields": [{
                            "key": "book_match", "label": "Matched book", "valueType": "text", "candidates": [],
                            "default": None, "agree": False, "evidenceIds": ["ev1"], "flags": []
                        }]
                    }]
                }]
            }
            old = {
                "meta": current["meta"],
                "items": [{
                    **current["items"][0],
                    "evidence": [{
                        "id": "ev1", "role": "pdf_page", "file": asset, "label": "Paper p. 2",
                        "sourceLine": "Paper p. 2 [sources/newspapers/paper.pdf]"
                    }]
                }]
            }
            overrides = {"schema": 1, "items": {}}
            input_path = root / "input.json"
            zip_path = root / "old.zip"
            overrides_path = root / "overrides.json"
            output_path = root / "output.json"
            report_path = root / "report.json"
            input_path.write_text(json.dumps(current), encoding="utf-8")
            overrides_path.write_text(json.dumps(overrides), encoding="utf-8")
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("dataset.json", json.dumps(old))

            subprocess.run([
                sys.executable, str(TOOLS / "repair_ground_truth_dataset.py"),
                "--input", str(input_path), "--old-zip", str(zip_path),
                "--asset-root", str(root), "--overrides", str(overrides_path),
                "--output", str(output_path), "--report", str(report_path),
            ], check=True, capture_output=True, text=True)

            repaired = json.loads(output_path.read_text(encoding="utf-8"))
            item = repaired["items"][0]
            self.assertNotIn("alert", item)
            self.assertEqual(item["evidence"][0]["role"], "pdf_page")
            self.assertEqual(item["evidence"][0]["sourceKind"], "newspaper")
            self.assertEqual(item["books"][0]["fields"], [])
            self.assertNotIn("bridge", json.dumps(item).lower())
            self.assertNotIn("edition is assigned", json.dumps(item).lower())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(len(report["relinked"]), 1)

            validation = subprocess.run([
                sys.executable, str(TOOLS / "validate_ground_truth_dataset.py"),
                str(output_path), "--asset-root", str(root),
            ], check=True, capture_output=True, text=True)
            self.assertTrue(json.loads(validation.stdout)["ok"])

    def test_override_clears_stale_text_and_can_block_a_wrong_relink(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "assets").mkdir()
            asset = "assets/page.jpg"
            (root / asset).write_bytes(b"test image placeholder")
            evidence = [
                {"id": "ev1", "role": "text", "label": "Correct page", "sourceLine": "Correct page",
                 "text": "File: sources/report.pdf\nNot shipped: assets disabled."},
                {"id": "ev2", "role": "text", "label": "Wrong page", "sourceLine": "Wrong page",
                 "text": "File: sources/wrong.pdf\nNot shipped: assets disabled."},
                {"id": "ev3", "role": "pdf_page", "label": "Stale visual", "sourceLine": "Wrong scan",
                 "file": asset, "page": {"pdfIndex": 1}, "regions": [{"x": 0, "y": 0, "w": 1, "h": 1}]},
            ]
            current = {
                "meta": {"name": "test", "schema": 3, "nItems": 1},
                "items": [{
                    "id": "evt1", "groupKey": "AR|test|1898", "group": "conflicts", "title": "Test",
                    "subtitle": "Arkansas", "state": "AR", "year": 1898, "priority": 0.5,
                    "evidence": evidence, "books": [],
                }],
            }
            old = json.loads(json.dumps(current))
            old["items"][0]["evidence"] = [
                {"id": "ev1", "role": "pdf_page", "file": asset, "sourceLine": "Correct page"},
                {"id": "ev2", "role": "pdf_page", "file": asset, "sourceLine": "Wrong page"},
                {"id": "ev3", "role": "pdf_page", "file": asset, "sourceLine": "Wrong scan"},
            ]
            overrides = {"schema": 1, "items": {"evt1": {
                "block_visual_relinks": ["ev2"],
                "replace_evidence": {
                    "ev1": {"role": "pdf_page", "file": asset},
                    "ev3": {"role": "text", "text": "The cited page is unavailable."},
                },
            }}}
            input_path = root / "input.json"
            zip_path = root / "old.zip"
            overrides_path = root / "overrides.json"
            output_path = root / "output.json"
            report_path = root / "report.json"
            input_path.write_text(json.dumps(current), encoding="utf-8")
            overrides_path.write_text(json.dumps(overrides), encoding="utf-8")
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("dataset.json", json.dumps(old))

            subprocess.run([
                sys.executable, str(TOOLS / "repair_ground_truth_dataset.py"),
                "--input", str(input_path), "--old-zip", str(zip_path),
                "--asset-root", str(root), "--overrides", str(overrides_path),
                "--output", str(output_path), "--report", str(report_path),
            ], check=True, capture_output=True, text=True)

            repaired = json.loads(output_path.read_text(encoding="utf-8"))["items"][0]
            by_id = {entry["id"]: entry for entry in repaired["evidence"]}
            self.assertEqual(by_id["ev1"]["role"], "pdf_page")
            self.assertNotIn("text", by_id["ev1"])
            self.assertEqual(by_id["ev2"]["role"], "text")
            self.assertEqual(by_id["ev3"]["role"], "text")
            self.assertNotIn("file", by_id["ev3"])
            self.assertNotIn("page", by_id["ev3"])
            self.assertNotIn("regions", by_id["ev3"])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["blocked_by_override"], [["evt1", "ev2"]])


if __name__ == "__main__":
    unittest.main()
