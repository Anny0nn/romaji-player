"""Free recognition may merge token envelopes but cannot divide mora ownership."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from free_phone_words import observe_words


def posterior(labels, width):
    p = np.full((len(labels), width), 0.01 / (width - 1))
    p[np.arange(len(labels)), labels] = 0.99
    return np.log(p)


class FreePhoneWords(unittest.TestCase):
    def words(self, phones):
        return [{"raw_span": [i, i + 1], "phones": p} for i, p in enumerate(phones)]

    def test_complete_word_uses_actual_free_token_frames_and_confidence(self):
        vocab = {1: ["a"], 2: ["b"], 3: ["c"], 4: ["d"], 5: ["e"], 6: ["f"]}
        logp = posterior([0, 1, 1, 2, 2, 3, 3, 0, 4, 4, 5, 5, 6, 6, 0], 7)
        units = observe_words(
            logp,
            0,
            self.words([["a", "b"], ["c", "d"], ["e", "f"]]),
            vocab,
            frame_ms=20,
            receptive_ms=25,
        )
        self.assertEqual([u["source_match"] for u in units], [False, True, False])
        self.assertEqual((units[1]["start_ms"], units[1]["end_ms"]), (100, 205))
        self.assertAlmostEqual(units[1]["probability"], 0.99)
        self.assertFalse(units[1]["source_conditioned"])
        # Changing source text never changes the acoustic token sequence.
        changed = observe_words(
            logp,
            0,
            self.words([["a", "b"], ["x", "d"], ["e", "f"]]),
            vocab,
            frame_ms=20,
            receptive_ms=25,
        )
        self.assertFalse(changed[1]["source_match"])

    def test_a_decoder_mora_that_straddles_source_words_cannot_verify_either(self):
        vocab = {1: ["a", "b"], 2: ["c", "d"], 3: ["e", "f"], 4: ["g", "h"]}
        logp = posterior([1, 1, 0, 2, 2, 0, 3, 3, 0, 4, 4], 5)
        units = observe_words(
            logp,
            0,
            self.words([["a", "b", "c"], ["d", "e"], ["f", "g", "h"]]),
            vocab,
            frame_ms=10,
            receptive_ms=10,
        )
        self.assertFalse(any(u["source_match"] for u in units))

    def test_repeated_context_and_unsupported_source_are_withheld(self):
        vocab = {i: [str(i)] for i in range(1, 7)}
        labels = [1, 2, 3, 4, 5, 6]
        logp = posterior(labels + [0] + labels, 7)
        units = observe_words(
            logp,
            0,
            self.words([["1", "2"], ["3", "4"], ["5", "6"]]),
            vocab,
            frame_ms=10,
            receptive_ms=10,
        )
        self.assertFalse(any(u["source_match"] for u in units))
        units = observe_words(
            posterior(labels, 7),
            0,
            self.words([["1", "2"], None, ["5", "6"]]),
            vocab,
            frame_ms=10,
            receptive_ms=10,
        )
        self.assertFalse(any(u["source_match"] for u in units))

    def test_invalid_posteriors_or_clock_are_rejected(self):
        with self.assertRaises(ValueError):
            observe_words(
                posterior([0, 1], 2) + 0.1,
                0,
                self.words([["a"]]),
                {1: ["a"]},
                frame_ms=10,
                receptive_ms=10,
            )
        with self.assertRaises(ValueError):
            observe_words(
                posterior([0, 1], 2),
                0,
                self.words([["a"]]),
                {1: ["a"]},
                frame_ms=0,
                receptive_ms=10,
            )

    def test_word_only_trial_keeps_whole_word_despite_wrong_neighbor(self):
        vocab = {i: [str(i)] for i in range(1, 9)}
        words = self.words([["8"], ["2", "3", "4", "5", "6", "7"], None])
        logp = posterior([1, 2, 3, 4, 5, 6, 7, 8], 9)
        common = {"frame_ms": 10, "receptive_ms": 10}
        self.assertFalse(
            observe_words(logp, 0, words, vocab, **common)[1]["source_match"]
        )
        trial = observe_words(
            logp, 0, words, vocab, context_phones=0, minimum_word_phones=6, **common
        )
        self.assertTrue(trial[1]["source_match"])
        self.assertEqual(trial[1]["observed_token_span"], [1, 7])
        self.assertFalse(trial[2]["source_match"])

    def test_word_only_trial_withholds_short_or_repeated_words(self):
        vocab = {i: [str(i)] for i in range(1, 7)}
        words = self.words([["1", "2"], ["3", "4"], ["5", "6"]])
        for labels, minimum in [([1, 2, 3, 4, 5, 6], 3), ([1, 2, 3, 4, 3, 4, 5, 6], 2)]:
            result = observe_words(
                posterior(labels, 7),
                0,
                words,
                vocab,
                frame_ms=10,
                receptive_ms=10,
                context_phones=0,
                minimum_word_phones=minimum,
            )
            self.assertFalse(result[1]["source_match"])
