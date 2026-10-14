"""Pronunciation aliases are bounded hypotheses, preserving distinct phone paths."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from english_singing_phones import japanese_hypothesis


class EnglishSingingPhones(unittest.TestCase):
    def test_fixed_loan_and_direct_paths_are_distinct_without_dropping_source_word(
        self,
    ):
        self.assertEqual(
            japanese_hypothesis(["b", "ao", "r", "n"], "loan"), ["b", "o", "o", "N"]
        )
        self.assertEqual(
            japanese_hypothesis(["b", "ao", "r", "n"], "direct"), ["b", "o", "r", "N"]
        )
        self.assertEqual(
            japanese_hypothesis(["b", "l", "ih", "ng"], "loan"),
            ["b", "u", "r", "i", "N"],
        )

    def test_unknown_phone_or_mode_never_gets_guessed(self):
        self.assertIsNone(japanese_hypothesis(["b", "undocumented"], "loan"))
        self.assertIsNone(japanese_hypothesis([], "direct"))
        with self.assertRaises(ValueError):
            japanese_hypothesis(["aa"], "other")


if __name__ == "__main__":
    unittest.main()
