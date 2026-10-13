"""Unknown phones and word markers cannot masquerade as acoustic evidence."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from english_phone_reference import labels, phrase_groups, tokens


class EnglishPhones(unittest.TestCase):
    def test_seconds_word_markers_silence_and_unknown_uncertainty(self):
        rows = labels("0 .1 sil\n.1 .2 k\n.2 .3 ah\n.3 .3 sp\n.3 .5 ay\n.5 .6 sil", 600)
        groups = list(phrase_groups(rows))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][1]["end_ms"], 300)
        self.assertEqual([r["word"] for r in groups[0]], [0, 0, 1])
        self.assertIsNone(rows[1]["uncertainty_ms"])

    def test_er_or_other_missing_phone_abstains_for_whole_phrase(self):
        for phone in ("er", "unknown", "AH"):
            self.assertIsNone(
                tokens([{"phone": "k"}, {"phone": phone}], {"k": 1, "ʌ": 2})
            )
        self.assertEqual(
            tokens([{"phone": "k"}, {"phone": "ah"}], {"k": 1, "ʌ": 2}), [1, 2]
        )

    def test_positive_word_marker_overlap_and_bad_timestamps_fail(self):
        for text in ("0 .1 sp", ".1 .1 k", ".1 .3 k\n.2 .4 a", "nan .3 k", "0 .7 k"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                labels(text, 600)
