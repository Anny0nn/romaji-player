import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from joint_source_windows import join_cues, reattach_units


class JointSourceWindows(unittest.TestCase):
    def fixture(self):
        crops = [
            {
                "occurrence": n,
                "start_sample": 16000 + n * 4000,
                "end_sample": 24000 + n * 4000,
                "raw_line": "空へ",
                "source_word_count": 2,
                "targets": [
                    {"raw_span": [0, 3], "text": "そら", "romaji": "sora"},
                    {"raw_span": [3, 6], "text": "へ", "romaji": "e"},
                ],
            }
            for n in (0, 1)
        ]
        occurrences = {n: {"raw_line": "空へ", "fragments": []} for n in (0, 1)}
        occurrences[0]["fragments"] = [
            {"raw_span": [0, 3], "interval": {"start_ms": 900, "end_ms": 1100}}
        ]
        return crops, occurrences

    def test_repeated_lines_have_distinct_owners_and_exact_utf8_clock_mapping(self):
        crops, occurrences = self.fixture()
        joined = join_cues(crops, occurrences, 16000, 28000)
        self.assertEqual(
            [u["raw_span"] for u in joined["targets"]],
            [[0, 3], [3, 6], [7, 10], [10, 13]],
        )
        self.assertEqual(joined["baseline"][0]["start_ms"], -100)
        self.assertTrue(joined["baseline"][0]["protected"])
        units = [
            {**t, "start_ms": 10 + n * 100, "end_ms": 90 + n * 100}
            for n, t in enumerate(joined["targets"])
        ]
        units[1].update(start_ms=-1, end_ms=-1)
        mapped = reattach_units(joined, units)
        self.assertEqual(
            mapped[1][0], {"raw_span": [0, 3], "start_ms": 1210, "end_ms": 1290}
        )
        self.assertEqual(mapped[0][1]["start_ms"], -1)
        self.assertEqual(crops[1]["targets"][0]["raw_span"], [0, 3])

    def test_rejects_outside_crops_duplicate_occurrences_and_split_bytes(self):
        crops, occurrences = self.fixture()
        for bad in ([crops[0], crops[0]], list(reversed(crops))):
            with self.assertRaises(ValueError):
                join_cues(bad, occurrences, 16000, 28000)
        with self.assertRaises(ValueError):
            join_cues(crops, occurrences, 16001, 28000)
        crops[0]["targets"][0]["raw_span"] = [0, 2]
        with self.assertRaises(ValueError):
            join_cues(crops, occurrences, 16000, 28000)

    def test_reattachment_does_not_clip_reorder_or_repair_bad_predictions(self):
        crops, occurrences = self.fixture()
        joined = join_cues(crops, occurrences, 16000, 28000)
        units = [{**t, "start_ms": 0, "end_ms": 100} for t in joined["targets"]]
        units[0]["end_ms"] = 751
        with self.assertRaises(ValueError):
            reattach_units(joined, units)
        units[0]["end_ms"] = 100
        units[0]["raw_span"] = [1, 2]
        with self.assertRaises(ValueError):
            reattach_units(joined, units)
