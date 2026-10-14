"""Wrong readings and withheld intervals cannot count as joint correct repairs."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "timing_summary", Path(__file__).resolve().parents[1] / "time-reading-admissions.py"
)
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


class ReadingTimingSummary(unittest.TestCase):
    def test_withheld_and_wrong_readings_remain_in_admission_denominator(self):
        correct = {
            "recording": "synthetic",
            "interval": {"start_ms": 100, "end_ms": 500},
            "correct_reading": True,
            "joint_correct": True,
            "onset_error_ms": 0,
            "offset_error_ms": 0,
        }
        missing = {
            **correct,
            "interval": {"start_ms": -1, "end_ms": -1},
            "joint_correct": False,
            "onset_error_ms": None,
            "offset_error_ms": None,
        }
        wrong = {**correct, "correct_reading": False, "joint_correct": False}
        result = timing.summarize([correct, missing, wrong])
        self.assertEqual(
            (
                result["admitted"],
                result["retained_timings"],
                result["correct_readings_with_timing"],
                result["joint_correct"],
            ),
            (3, 2, 1, 1),
        )
        self.assertEqual(result["joint_fraction_of_admissions"], 1 / 3)
        self.assertIsNone(timing.summarize([])["joint_fraction_of_admissions"])


if __name__ == "__main__":
    unittest.main()
