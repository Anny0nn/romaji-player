"""Long recognition context cannot silently alter original Rust sample bounds."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

spec = importlib.util.spec_from_file_location(
    "capped_cache", Path(__file__).resolve().parents[1] / "cache-capped-singing.py"
)
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


class ContextWindowTests(unittest.TestCase):
    def test_unions_whole_crops_and_keeps_each_occurrence_covered(self):
        crops = [
            {"start_sample": i * 90, "end_sample": i * 90 + 120, "occurrence": i}
            for i in range(7)
        ]
        windows = cache.context_windows(crops, 400)
        self.assertEqual(
            windows[0],
            {"first_sample": 0, "last_sample": 390, "occurrences": [0, 1, 2, 3]},
        )
        self.assertEqual({i for w in windows for i in w["occurrences"]}, set(range(7)))
        for window in windows:
            members = [crops[i] for i in window["occurrences"]]
            self.assertEqual(
                window["first_sample"], min(c["start_sample"] for c in members)
            )
            self.assertEqual(
                window["last_sample"], max(c["end_sample"] for c in members)
            )
            self.assertLessEqual(window["last_sample"] - window["first_sample"], 400)

    def test_short_single_crop_and_nested_crop_preserve_exact_end(self):
        self.assertEqual(
            cache.context_windows(
                [{"start_sample": 7, "end_sample": 17, "occurrence": 2}]
            ),
            [{"first_sample": 7, "last_sample": 17, "occurrences": [2]}],
        )
        crops = [
            {"start_sample": 0, "end_sample": 100, "occurrence": 0},
            {"start_sample": 10, "end_sample": 80, "occurrence": 1},
        ]
        self.assertEqual(cache.context_windows(crops, 100)[0]["last_sample"], 100)

    def test_unordered_float_degenerate_and_overlong_crops_are_rejected(self):
        for rows in (
            [],
            [{"start_sample": 0, "end_sample": 501}],
            [{"start_sample": 0.0, "end_sample": 100}],
            [{"start_sample": 10, "end_sample": 10}],
            [
                {"start_sample": 20, "end_sample": 40},
                {"start_sample": 10, "end_sample": 30},
            ],
        ):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                cache.context_windows(rows, 500)
