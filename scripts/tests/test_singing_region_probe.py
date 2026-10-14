"""New gaps cannot borrow clocks or erase protected / contradictory neighbors."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from singing_region_probe import recover_regions


class RegionProbeTests(unittest.TestCase):
    def setUp(self):
        self.baseline = [
            {"raw_span": [i, i + 1], "start_ms": start, "end_ms": end}
            for i, (start, end) in enumerate(
                [(100, 350), (-1, -1), (500, 900), (1000, 1200)]
            )
        ]
        self.units = [
            {**old, "start_ms": start, "end_ms": end}
            for old, (start, end) in zip(
                self.baseline,
                [(110, 340), (450, 650), (660, 770), (990, 1210)],
                strict=True,
            )
        ]
        self.trial = {
            "units": self.units,
            "raw_units": [{**u, "reason": "retained"} for u in self.units],
        }
        self.evidence = [{**u, "mean_probability": 0.8} for u in self.units]

    def run_trial(self, **kwargs):
        return recover_regions(
            self.baseline,
            self.trial,
            self.evidence,
            1500,
            kwargs.pop("source_words", 4),
            **kwargs,
        )

    def test_fresh_pair_can_repair_automatic_neighbor_and_add_gap(self):
        original = copy.deepcopy(self.baseline)
        result, events = self.run_trial()
        self.assertEqual(
            [(r["start_ms"], r["end_ms"]) for r in result],
            [(100, 350), (450, 650), (660, 770), (1000, 1200)],
        )
        self.assertEqual(
            events,
            [{"region": [1, 2], "reason": "paired_region", "added": 1, "moved": 1}],
        )
        self.assertEqual(self.baseline, original)

    def test_protected_neighbor_or_gap_never_changes(self):
        for protected in ([1], [2]):
            with self.subTest(protected=protected):
                result, _ = self.run_trial(protected=protected)
                self.assertEqual(result, self.baseline)

    def test_two_models_must_contradict_the_old_boundary(self):
        self.evidence[2].update(start_ms=650, end_ms=780)
        result, events = self.run_trial()
        self.assertEqual(result, self.baseline)
        self.assertEqual(events[0]["reason"], "old_boundary_not_contradicted_twice")

    def test_weak_probability_or_disagreeing_endpoint_does_not_repair(self):
        for change in ({"mean_probability": 0.44}, {"end_ms": 950}):
            with self.subTest(change=change):
                evidence = copy.deepcopy(self.evidence)
                evidence[2].update(change)
                result, events = recover_regions(
                    self.baseline, self.trial, evidence, 1500, 4
                )
                self.assertEqual(result, self.baseline)
                self.assertEqual(events[0]["reason"], "unsupported_region_word")

    def test_outer_anchor_needs_fresh_support_on_both_endpoints(self):
        self.evidence[0]["end_ms"] = 550
        result, events = self.run_trial()
        self.assertEqual(result, self.baseline)
        self.assertEqual(events[0]["reason"], "unverified_outer_anchor")

    def test_real_observation_overlap_is_not_trimmed(self):
        self.units[1]["end_ms"] = 700
        self.trial["raw_units"][1]["end_ms"] = 700
        self.evidence[1]["end_ms"] = 700
        result, events = self.run_trial()
        self.assertEqual(result, self.baseline)
        self.assertEqual(events[0]["reason"], "observed_interval_overlap")

    def test_omitted_original_groups_cannot_be_treated_as_adjacent(self):
        result, events = self.run_trial(source_words=5)
        self.assertEqual(result, self.baseline)
        self.assertEqual(events, [{"reason": "unmapped_original_groups"}])

    def test_source_ownership_changes_are_rejected(self):
        self.evidence[1]["raw_span"] = [9, 10]
        with self.assertRaisesRegex(ValueError, "ownership"):
            self.run_trial()
