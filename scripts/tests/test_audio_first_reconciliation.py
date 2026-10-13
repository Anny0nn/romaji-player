"""Audio-first repairs retain Japanese byte ownership and ambiguous spelling."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_first_reconciliation import baseline_first, envelopes, kana_candidates


class ReconciliationTests(unittest.TestCase):
    def test_fixed_fallback_priority_cannot_peek_at_reference_correctness(self):
        base = {
            "case": "1",
            "condition": "injected",
            "method": "current-core",
            "selected": "old",
            "correct": False,
        }
        proposal = {**base, "method": "romaji-beam", "selected": "new", "correct": True}
        self.assertEqual(baseline_first([proposal, base])[0]["selected"], "old")
        self.assertEqual(baseline_first([proposal])[0]["selected"], "new")
        with self.assertRaises(ValueError):
            baseline_first([proposal, proposal])

    def words(self, text):
        return [
            {"raw_span": [i * 3, (i + 1) * 3], "expected_text": value}
            for i, value in enumerate(text)
        ]

    def test_acoustic_unknown_reading_attaches_to_original_japanese_bytes(self):
        raw = "前闇後"
        left, right = ["h", "i", "z", "a", "sh", "i"], ["o", "k", "u", "n", "i"]
        readings = [left, ["a", "N", "y", "a"], right]
        observed = left + ["y", "a", "m", "i", "y", "o"] + right
        patches = envelopes(raw, self.words(raw), observed, readings)
        self.assertEqual(patches[0]["raw_span"], [3, 6])
        self.assertEqual(patches[0]["phones"], ["y", "a", "m", "i", "y", "o"])
        self.assertEqual(patches[0]["expected_text"], "闇")

    def test_unchanged_control_and_unknown_symbols_never_propose(self):
        raw, phones = "前中後", [["m", "a"], ["n", "a"], ["k", "o"]]
        self.assertEqual(
            envelopes(
                raw, self.words(raw), [p for group in phones for p in group], phones
            ),
            [],
        )
        self.assertEqual(
            envelopes(raw, self.words(raw), ["unsupported:word"], phones), []
        )

    def test_utf8_mismatch_is_not_reattached_by_substring_search(self):
        words = self.words("前中後")
        words[1]["raw_span"] = [2, 6]
        with self.assertRaises((ValueError, UnicodeDecodeError)):
            envelopes(
                "前中後",
                words,
                ["a", "a", "i", "o", "o"],
                [["a", "a"], ["u"], ["o", "o"]],
            )

    def test_inverse_mapping_does_not_guess_homophonic_kana(self):
        self.assertEqual(
            kana_candidates(["j", "i"], {("j", "i"): ["じ", "ぢ"]}), ["じ", "ぢ"]
        )
        self.assertEqual(kana_candidates(["unknown"], {("a",): ["あ"]}), [])
        self.assertEqual(kana_candidates(["a"], {("a",): ["あ", "ぁ"]}, limit=1), [])

    def test_line_edges_and_unanchored_lyric_insertions_are_withheld(self):
        words = self.words("前中後")
        readings = [["m", "a", "e"], ["n", "a"], ["a", "t", "o"]]
        self.assertEqual(
            envelopes(
                "前中後",
                words,
                ["s", "o", "r", "a"] + readings[1] + readings[2],
                readings,
            ),
            [],
        )
        original = [p for group in readings for p in group]
        self.assertEqual(
            envelopes(
                "前中後", words, original[:3] + ["k", "o"] + original[3:], readings
            ),
            [],
        )

    def test_split_original_words_keep_one_exact_complete_group_envelope(self):
        raw = "前食べた後"
        words = [
            {"raw_span": [0, 3], "expected_text": "前"},
            {"raw_span": [3, 9], "expected_text": "食べ"},
            {"raw_span": [9, 12], "expected_text": "た"},
            {"raw_span": [12, 15], "expected_text": "後"},
        ]
        left, right = (
            ["h", "i", "z", "a", "sh", "i", "ch", "i"],
            ["o", "k", "u", "n", "i"],
        )
        reading = [left, ["t", "a", "b", "e"], ["t", "a"], right]
        observed = left + ["n", "o", "m", "u"] + right
        patches = envelopes(raw, words, observed, reading)
        self.assertEqual(
            [(p["raw_span"], p["expected_text"]) for p in patches],
            [([3, 12], "食べた")],
        )


if __name__ == "__main__":
    unittest.main()
