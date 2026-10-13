"""Reference granularity and unknown-phone abstentions cannot drift silently."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from singing_groups import groups, phrases


class Groups(unittest.TestCase):
    def labels(self, symbols):
        return [
            {"phone": p, "start_ms": i * 40, "end_ms": (i + 1) * 40}
            for i, p in enumerate(symbols)
        ]

    def test_groups_keep_complete_phones_original_boundaries_and_utf8(self):
        result = groups(
            self.labels(["ky", "a", "N", "a"]),
            {("ky", "a"): "きゃ", ("N",): "ん", ("a",): "あ"},
        )
        self.assertEqual([r["raw_span"] for r in result], [[0, 9], [9, 12]])
        self.assertEqual(result[0]["phone"], "ky a N")
        self.assertEqual(result[0]["end_ms"], 120)
        self.assertEqual(result[1]["start_ms"], 120)

    def test_unknown_inventory_abstains_instead_of_erasing_part_of_phrase(self):
        inventory = {("a",): "あ"}
        for phone in ["I", "U", "O", "cl", "unknown"]:
            self.assertIsNone(groups(self.labels(["a", phone, "a"]), inventory))

    def test_silence_is_a_phrase_boundary_and_never_a_sung_unit(self):
        self.assertEqual(
            [
                [p["phone"] for p in row]
                for row in phrases(self.labels(["pau", "a", "pau", "N"]))
            ],
            [["a"], ["N"]],
        )
