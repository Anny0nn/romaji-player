"""Nonfinite model fields cannot turn into valid invented timestamp zeroes."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "timing_crops", Path(__file__).resolve().parents[1] / "transcribe-timing-crops.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class UndefinedObservations(unittest.TestCase):
    def test_undefined_stats_and_times_remain_null_without_changing_valid_word(self):
        value = {
            "avg_logprob": float("nan"),
            "words": [
                {"word": "sing", "start": 1.2, "end": float("inf"), "probability": 0.9}
            ],
        }
        result = runner.finite_json(value)
        self.assertIsNone(result["avg_logprob"])
        self.assertIsNone(result["words"][0]["end"])
        self.assertEqual(result["words"][0]["start"], 1.2)
        self.assertEqual(result["words"][0]["word"], "sing")


if __name__ == "__main__":
    unittest.main()
