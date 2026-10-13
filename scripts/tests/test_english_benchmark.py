"""Human word markers preserve incomplete alignments and original boundaries."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "english_benchmark",
    Path(__file__).resolve().parents[1] / "benchmark-english-phones.py",
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class EnglishWordGroups(unittest.TestCase):
    def test_word_boundaries_are_not_invented_for_incomplete_phone_path(self):
        reference = [
            {"word": word, "phone": phone, "start_ms": start, "end_ms": end}
            for word, phone, start, end in [
                (0, "k", 10, 40),
                (0, "ah", 40, 200),
                (1, "iy", 300, 500),
            ]
        ]
        predicted = [
            {"start_ms": start, "end_ms": end, "mean_probability": p}
            for start, end, p in [(20, 50, 0.9), (-1, -1, 0), (310, 510, 0.8)]
        ]
        result = benchmark.word_records(
            [{"id": "synthetic", "reference": reference, "predicted": predicted}]
        )[0]
        self.assertEqual([r["unit"] for r in result["reference"]], [0, 1])
        self.assertEqual(result["reference"][0]["phone"], "k ah")
        self.assertEqual(
            (result["reference"][0]["start_ms"], result["reference"][0]["end_ms"]),
            (10, 200),
        )
        self.assertEqual(result["predicted"][0]["start_ms"], -1)
        self.assertEqual(
            (result["predicted"][1]["start_ms"], result["predicted"][1]["end_ms"]),
            (310, 510),
        )

    def test_low_probability_complete_path_is_an_abstention(self):
        row = {
            "id": "synthetic",
            "reference": [{"word": 0, "phone": "aa", "start_ms": 0, "end_ms": 200}],
            "predicted": [{"start_ms": 0, "end_ms": 200, "mean_probability": 0.44}],
        }
        result = benchmark.word_records([row])[0]
        self.assertEqual(result["predicted"][0]["start_ms"], -1)
        self.assertEqual(result["predicted"][0]["end_ms"], -1)
