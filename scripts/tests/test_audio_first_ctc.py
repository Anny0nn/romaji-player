"""Blind CTC must match exhaustive paths and count missing/extra pronunciation."""

import itertools
import math
import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_first_ctc import beam, edit_counts, greedy, phone_hypotheses


class BlindCTCTests(unittest.TestCase):
    def test_prefix_sum_matches_exhaustive_ctc_paths_including_repeats(self):
        probabilities = [[0.2, 0.5, 0.3], [0.4, 0.2, 0.4], [0.1, 0.6, 0.3]]
        exact = defaultdict(float)
        for path in itertools.product(range(3), repeat=3):
            prefix, previous, value = [], None, 1.0
            for index, token in enumerate(path):
                value *= probabilities[index][token]
                if token and token != previous:
                    prefix.append(token)
                previous = token
            exact[tuple(prefix)] += value
        output = beam(
            [[math.log(v) for v in row] for row in probabilities],
            0,
            width=32,
            nbest=32,
            token_prune=0,
        )
        scored = {
            tuple(h["token_ids"]): math.exp(h["approximate_sequence_score"])
            for h in output
        }
        self.assertEqual(set(scored), set(exact))
        for sequence in exact:
            self.assertAlmostEqual(scored[sequence], exact[sequence])

    def test_greedy_blank_separates_repeated_tokens_and_retains_real_frames(self):
        rows = [[-4, -0.1], [-4, -0.1], [-0.1, -4], [-4, -0.1]]
        result = greedy(rows, 0)
        self.assertEqual(result["token_ids"], [1, 1])
        self.assertEqual(result["emission_frames"], [[0, 1], [3, 3]])

    def test_mora_and_split_phone_paths_are_one_phonetic_hypothesis(self):
        vocab = {1: ["ky", "a"], 2: ["ky"], 3: ["a"]}
        output = phone_hypotheses(
            [
                {"token_ids": [1], "approximate_sequence_score": math.log(0.3)},
                {"token_ids": [2, 3], "approximate_sequence_score": math.log(0.2)},
            ],
            lambda ids: [p for token in ids for p in vocab[token]],
        )
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["phones"], ["ky", "a"])
        self.assertEqual(output[0]["tokenizations"], 2)
        self.assertAlmostEqual(math.exp(output[0]["approximate_sequence_score"]), 0.5)

    def test_invalid_or_nonfinite_scores_and_bad_limits_are_rejected(self):
        for values in ([], [[]], [[math.nan]], [[math.inf]], [[-math.inf]]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                greedy(values, 0)
        with self.assertRaises(ValueError):
            beam([[-1, -1]], 0, nbest=3, width=2)

    def test_missing_extra_and_unknown_phones_are_counted_as_errors(self):
        result = edit_counts(["k", "a", "N"], ["k", "a", "unknown", "u"])
        self.assertEqual((result["substitutions"], result["insertions"]), (1, 1))
        self.assertEqual(edit_counts(["a", "a"], ["a"])["deletions"], 1)
        self.assertFalse(result["exact"])
        self.assertEqual(edit_counts([], ["a"])["insertions"], 1)


if __name__ == "__main__":
    unittest.main()
