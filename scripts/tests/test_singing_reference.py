"""Boundary metrics and sealed reference partitions must not flatter bad results."""

import copy
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from singing_reference import evaluate, htk_labels, selected_ids, verify_extracted


class ReferenceTests(unittest.TestCase):
    def test_extracted_reference_is_authenticated_by_frozen_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, archive = root / "labels.lab", root / "labels.zip"
            path.write_text("0 1000000 a")
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("nested/labels.lab", path.read_bytes())
            verify_extracted(archive, path)
            path.write_text("0 1000000 i")
            with self.assertRaisesRegex(ValueError, "Extracted"):
                verify_extracted(archive, path)
            with zipfile.ZipFile(archive, "a") as handle:
                handle.writestr("other/labels.lab", path.read_bytes())
            with self.assertRaisesRegex(ValueError, "Extracted"):
                verify_extracted(archive, path)

    def test_htk_units_gaps_silence_and_unknown_uncertainty(self):
        labels = htk_labels("0 1000000 pau\n1000000 1500000 k\n2000000 4000000 a", 500)
        self.assertEqual(labels[1]["end_ms"], 150)
        self.assertIsNone(labels[1]["uncertainty_ms"])
        for value in (
            "0 0 a",
            "0 3000000 a\n2000000 4000000 i",
            "0 6000000 a",
            "0 1 a extra",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                htk_labels(value, 500)

    def test_abstentions_are_not_correct_or_silently_dropped(self):
        refs = htk_labels("0 1000000 pau\n1000000 2000000 k\n2000000 3000000 a", 300)
        units = copy.deepcopy(refs)
        units[2].update(start_ms=-1, end_ms=-1)
        result = evaluate([{"id": "phrase", "reference": refs, "predicted": units}])
        self.assertEqual(
            (result["reference_units"], result["aligned_units"], result["abstentions"]),
            (2, 1, 1),
        )
        self.assertEqual(result["joint_fraction"], 1)
        self.assertLess(result["wilson_95_descriptive"][0], 1)
        self.assertFalse(result["recognition_accuracy_measured"])

    def test_wrong_phone_or_bad_interval_cannot_score(self):
        ref = htk_labels("0 2000000 a", 200)
        for change in ({"phone": "i"}, {"start_ms": float("nan")}, {"end_ms": -1}):
            predicted = [{**ref[0], **change}]
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluate([{"id": "p", "reference": ref, "predicted": predicted}])

    def test_reserved_ids_require_exact_frozen_receipt(self):
        split = {"development": ["a"], "heldout": ["b"]}
        expected = {"recipe": "sha", "assets": "sha"}
        self.assertEqual(selected_ids(split, "development", None, expected), ["a"])
        for receipt in (None, {"recipe": "old", "assets": "sha"}):
            with self.assertRaises(ValueError):
                selected_ids(split, "heldout", receipt, expected)
        self.assertEqual(selected_ids(split, "heldout", expected, expected), ["b"])
        split["heldout"] = ["a"]
        with self.assertRaises(ValueError):
            selected_ids(split, "development", None, expected)
