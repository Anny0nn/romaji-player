"""Reference scores use absolute sample clocks and retain changed abstentions."""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "context_benchmark", ROOT / "scripts/benchmark-singing-context.py"
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class ContextBenchmark(unittest.TestCase):
    def case(self):
        return (
            [(0, 16000, 32000, [])],
            [[{"unit": 0, "phone": "k a", "start_ms": 1200, "end_ms": 1500}]],
            ["song:phrase"],
            [[{"start_ms": 200, "end_ms": 500}]],
        )

    def test_sample_origin_applies_once_and_recovered_span_is_reference_scored(self):
        crops, refs, owners, correct = self.case()
        report, _ = benchmark.score(
            crops, refs, owners, [[{"start_ms": -1, "end_ms": -1}]], correct
        )
        self.assertEqual(report["new_units"], 1)
        self.assertEqual(report["metrics"]["affected"]["joint_fraction"], 1)
        self.assertFalse(report["timing_reference_gate_passed"])
        self.assertFalse(report["metrics"]["affected"]["recognition_accuracy_measured"])

    def test_missing_candidate_stays_missing_after_nonzero_origin(self):
        crops, refs, owners, correct = self.case()
        report, _ = benchmark.score(
            crops, refs, owners, correct, [[{"start_ms": -1, "end_ms": -1}]]
        )
        self.assertEqual(report["lost_units"], 1)
        self.assertEqual(report["regressed_correct_units"], 1)
        self.assertEqual(report["metrics"]["affected"]["abstentions"], 1)

    def test_bad_new_timing_and_moved_correct_timing_cannot_flatter_gate(self):
        crops, refs, owners, correct = self.case()
        wrong = [[{"start_ms": 450, "end_ms": 700}]]
        report, _ = benchmark.score(crops, refs, owners, correct, wrong)
        self.assertEqual(report["regressed_correct_units"], 1)
        self.assertEqual(report["metrics"]["affected"]["joint_fraction"], 0)
