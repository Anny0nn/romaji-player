"""A mixed-token path cannot manufacture phone times or cross source words."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from singing_word_alignment import word_alignment


class SingingWordAlignment(unittest.TestCase):
    def words(self, *values):
        return [
            {"text": value, "romaji": "reference", "raw_span": [i * 3, (i + 1) * 3]}
            for i, value in enumerate(values)
        ]

    def posterior(self, labels, width):
        probability = np.full((len(labels), width), 0.001)
        for index, label in enumerate(labels):
            probability[index, label] = 0.99
        return np.log(probability)

    def test_observed_mora_endpoints_and_repeated_word_spans(self):
        units = word_alignment(
            self.posterior([0, 3, 3, 0, 2, 2, 0], 4),
            0,
            self.words("か", "あ"),
            {"_": 0, "k": 1, "a": 2, "ka": 3},
        )
        self.assertEqual(
            [(u["start_ms"], u["end_ms"]) for u in units], [(20, 65), (80, 125)]
        )
        self.assertEqual([u["raw_span"] for u in units], [[0, 3], [3, 6]])
        self.assertTrue(all(abs(u["mean_probability"] - 0.99) < 1e-8 for u in units))

    def test_mora_cannot_straddle_two_source_words(self):
        vocabulary = {"_": 0, "aka": 1}
        units = word_alignment(
            self.posterior([1, 1, 0], 2), 0, self.words("あ", "か"), vocabulary
        )
        self.assertTrue(all(u["start_ms"] == -1 for u in units))
        joined = word_alignment(
            self.posterior([1, 1, 0], 2), 0, self.words("あか"), vocabulary
        )
        self.assertEqual(joined[0]["start_ms"], 0)

    def test_repeated_vowel_tokens_require_a_real_blank(self):
        vocabulary = {"_": 0, "a": 1}
        words = self.words("あ", "あ")
        impossible = word_alignment(self.posterior([1], 2), 0, words, vocabulary)
        self.assertTrue(all(u["start_ms"] == -1 for u in impossible))
        units = word_alignment(self.posterior([1, 0, 1], 2), 0, words, vocabulary)
        self.assertEqual(
            [(u["start_ms"], u["end_ms"]) for u in units], [(0, 25), (40, 65)]
        )

    def test_unknown_and_nonfinite_targets_never_drop_a_word(self):
        units = word_alignment(
            self.posterior([1, 0], 2), 0, self.words("あ", "English"), {"_": 0, "a": 1}
        )
        self.assertEqual(len(units), 2)
        self.assertTrue(all(u["start_ms"] == -1 for u in units))
        with self.assertRaises(ValueError):
            word_alignment(np.array([[0, np.nan]]), 0, self.words("あ"), {"a": 1})

    def test_explicit_phone_hypothesis_keeps_english_source_word_ownership(self):
        words = self.words("English", "English")
        vocabulary = {"_": 0, "k": 1, "a": 2, "ka": 3}
        units = word_alignment(
            self.posterior([0, 3, 3, 0, 2, 2, 0], 4),
            0,
            words,
            vocabulary,
            word_phones=[["k", "a"], ["a"]],
        )
        self.assertEqual([u["raw_span"] for u in units], [w["raw_span"] for w in words])
        self.assertEqual(
            [(u["start_ms"], u["end_ms"]) for u in units], [(20, 65), (80, 125)]
        )
        self.assertTrue(all(w["text"] == "English" for w in words))
        with self.assertRaises(ValueError):
            word_alignment(
                self.posterior([1], 4), 0, words, vocabulary, word_phones=[["a"]]
            )
        missing = word_alignment(
            self.posterior([1], 4), 0, words, vocabulary, word_phones=[[], ["a"]]
        )
        self.assertTrue(all(u["start_ms"] == -1 for u in missing))
