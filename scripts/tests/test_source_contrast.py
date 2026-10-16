"""A decoder that can force text does not establish localized acoustic support."""

import importlib.util
import math
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from source_contrast_policy import recover_original_groups, supported

spec = importlib.util.spec_from_file_location(
    "source_observation", SCRIPTS / "observe-source-evidence.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SourceContrast(unittest.TestCase):
    def test_overlay_preserves_old_intervals_and_requires_adjacent_dual_evidence(self):
        baseline = [
            {"raw_span": [i * 2, i * 2 + 1], "start_ms": -1, "end_ms": -1}
            for i in range(3)
        ]
        baseline[0].update(start_ms=100, end_ms=300, protected=True)
        evidence = [
            {
                **u,
                "start_ms": 100 + i * 220,
                "end_ms": 300 + i * 220,
                "source_mean_log_probability": -0.3,
                "silence_contrast_nats": 1,
                "wrong_verse_contrast_nats": 1,
                "own_mask_drop_nats": 1,
                "localized_excess_nats": 0.5,
            }
            for i, u in enumerate(baseline)
        ]
        result = recover_original_groups(baseline, [evidence, evidence], 1000, 3)
        self.assertEqual(result[0], baseline[0])
        self.assertEqual([u["start_ms"] for u in result], [100, 320, 540])
        self.assertEqual(baseline[1]["start_ms"], -1)
        weaker = [{**u, "own_mask_drop_nats": 0} for u in evidence]
        self.assertEqual(
            recover_original_groups(baseline, [evidence, weaker], 1000, 3), baseline
        )
        collision = [{**u, "start_ms": u["start_ms"] - 100} for u in evidence]
        self.assertEqual(
            recover_original_groups(baseline, [collision, collision], 1000, 3)[1],
            baseline[1],
        )

    def test_protected_negative_crop_start_is_still_an_original_clock(self):
        old = [{"raw_span": [0, 1], "start_ms": -80, "end_ms": 200, "protected": True}]
        self.assertEqual(
            recover_original_groups(old, [[{**old[0]}], [{**old[0]}]], 1000, 1), old
        )
        with self.assertRaises(ValueError):
            recover_original_groups(old, [old, old], 1000, 0)

    def test_masks_keep_equal_sample_count_and_do_not_hide_the_candidate(self):
        for length, first, last in (
            (16000, 1000, 3000),
            (16000, 8000, 10000),
            (16000, 100, 15900),
        ):
            controls = runner.mask_controls(length, first, last)
            self.assertLessEqual(len(controls), 2)
            self.assertTrue(
                all(
                    b - a == last - first and (b <= first or a >= last)
                    for a, b in controls
                )
            )
        self.assertEqual(runner.mask_controls(16000, 100, 15900), [])
        with self.assertRaises(ValueError):
            runner.mask_controls(16000, -1, 100)

    def test_conditional_confidence_without_contrast_and_ablation_is_withheld(self):
        unit = {
            "start_ms": 100,
            "end_ms": 300,
            "source_mean_log_probability": -0.3,
            "silence_contrast_nats": 1,
            "wrong_verse_contrast_nats": 1,
            "own_mask_drop_nats": 1,
            "localized_excess_nats": 0.5,
        }
        self.assertTrue(supported(unit, 1000))
        for key in (
            "source_mean_log_probability",
            "silence_contrast_nats",
            "wrong_verse_contrast_nats",
            "own_mask_drop_nats",
            "localized_excess_nats",
        ):
            for value in (None, math.nan, True):
                self.assertFalse(supported({**unit, key: value}, 1000))
        self.assertFalse(supported({**unit, "own_mask_drop_nats": 0.1}, 1000))
        self.assertFalse(supported({**unit, "localized_excess_nats": -0.2}, 1000))
        self.assertFalse(supported({**unit, "end_ms": 1000}, 1000))
