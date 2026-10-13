"""Offline singing targets and source-word projection; no model or audio imports."""

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "singing", Path(__file__).resolve().parents[1] / "experiment-singing-phonemes.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def to_roma(kana):
    return {
        "ア": "a",
        "カ": "ka",
        "キ": "ki",
        "ャ": "xya",
        "ワ": "wa",
        "エ": "e",
        "オ": "o",
    }[kana]


class SingingTests(unittest.TestCase):
    def word(self, kana, romaji="a"):
        return {"raw_span": [0, len(kana.encode())], "hiragana": kana, "romaji": romaji}

    def test_contracted_sokuon_nasal_and_long_vowels_keep_upstream_inventory(self):
        self.assertEqual(
            module.syllables("きゃっかんー", to_roma),
            [["ky", "a"], ["cl"], ["k", "a"], ["N"]],
        )
        for text in ("", "English", "？", "ゃ"):
            self.assertIsNone(module.syllables(text, to_roma))

    def test_spoken_particles_and_repeated_phones_keep_source_word_owners(self):
        vocabulary = {"a": 1, "w": 2, "e": 3, "o": 4}
        words = [
            self.word("あ"),
            self.word("あ"),
            self.word("は", "wa"),
            self.word("へ", "e"),
            self.word("を", "o"),
        ]
        groups, owners, flat = module.targets(words, vocabulary, to_roma)
        self.assertEqual(groups, [[1], [39, 1], [2, 1], [3], [4]])
        self.assertEqual(owners, [0, None, 1, 2, 2, 3, 4])
        self.assertEqual(flat, [1, 39, 1, 2, 1, 3, 4])

    def test_unknown_or_blank_phone_withholds_line_without_dropping_words(self):
        words = [self.word("あ"), self.word("か")]
        for vocabulary in ({"a": 1}, {"a": 1, "k": 0}):
            self.assertIsNone(module.targets(words, vocabulary, to_roma))
        self.assertIsNone(module.targets([self.word("English")], {"a": 1}, to_roma))
        self.assertEqual(len(words), 2)

    def test_boundaries_do_not_extend_word_time_or_contribute_to_probability(self):
        words = [self.word("あ"), self.word("あ")]
        rows = [[0.0, 0.8] for _ in range(6)]
        result = module.word_intervals(
            words,
            [(0, 0.02), (0.02, 0.08), (0.08, 0.12)],
            [0, None, 1],
            [1, 39, 1],
            rows,
            0.12,
        )
        self.assertEqual(
            [(u["start_ms"], u["end_ms"]) for u in result], [(0, 20), (80, 120)]
        )
        self.assertTrue(all(abs(u["mean_probability"] - 0.8) < 1e-6 for u in result))

    def test_invalid_incomplete_or_outside_crop_intervals_stay_missing(self):
        words = [self.word("あ")]
        for intervals in ([], [(0, 0.14)], [(float("nan"), 0.12)], [(0, 0.001)]):
            result = module.word_intervals(
                words, intervals, [0], [1], [[0, 0.8]] * 6, 0.12
            )
            self.assertEqual(result[0]["start_ms"], -1)
        result = module.word_intervals(
            words, [(0, 0.12)], [0], [1], [[0, float("nan")]] * 6, 0.12
        )
        self.assertEqual(result[0]["mean_probability"], 0)

    def test_model_and_source_pin_fail_closed_before_import(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model"
            path.write_bytes(b"synthetic pinned weights")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            module.verified(path, digest)
            path.write_bytes(b"changed weights")
            with self.assertRaises(ValueError):
                module.verified(path, digest)


if __name__ == "__main__":
    unittest.main()
