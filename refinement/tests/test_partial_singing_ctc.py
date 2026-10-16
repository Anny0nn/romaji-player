"""Missing lyric words never obtain fabricated or divided acoustic frames."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from partial_singing_ctc import align_partial


def posterior(labels, width=5):
    values = np.full((len(labels), width), 0.001 / (width - 1))
    values[np.arange(len(labels)), labels] = 0.999
    return np.log(values)


class PartialSingingCTC(unittest.TestCase):
    def test_deleted_wrong_word_does_not_pull_later_word_or_receive_time(self):
        # The recording contains a, an unrelated x, then c; source inserts b.
        logp = posterior(
            [0] * 4 + [1] * 5 + [0] * 4 + [4] * 6 + [0] * 4 + [3] * 5 + [0] * 4
        )
        result = align_partial(
            logp, 0, [["a"], ["b"], ["c"]], {1: ["a"], 2: ["b"], 3: ["c"]}, margins=True
        )
        self.assertEqual(result["skipped_words"], [1])
        a, b, c = result["units"]
        self.assertEqual((a["start_ms"], a["end_ms"]), (80, 185))
        self.assertEqual((b["start_ms"], b["end_ms"]), (-1, -1))
        self.assertEqual((c["start_ms"], c["end_ms"]), (460, 565))
        self.assertGreater(a["deletion_margin_nats"], 0)
        self.assertIsNone(b["deletion_margin_nats"])
        self.assertAlmostEqual(c["mean_probability"], 0.999)

    def test_repeated_word_requires_an_actual_ctc_blank(self):
        words, vocabulary = [["a"], ["a"]], {1: ["a"]}
        continuous = align_partial(
            posterior([0] * 3 + [1] * 10 + [0] * 3), 0, words, vocabulary
        )
        self.assertEqual(sum(u["placed"] for u in continuous["units"]), 1)
        separate = align_partial(
            posterior([0] * 3 + [1] * 5 + [0] * 3 + [1] * 5 + [0] * 3),
            0,
            words,
            vocabulary,
        )
        self.assertTrue(all(u["placed"] for u in separate["units"]))

    def test_a_mora_cannot_be_split_between_words(self):
        logp = posterior([0] * 3 + [1] * 8 + [0] * 3)
        complete = align_partial(logp, 0, [["k", "a"]], {1: ["k", "a"]})
        self.assertEqual(
            (complete["units"][0]["start_ms"], complete["units"][0]["end_ms"]),
            (60, 225),
        )
        split = align_partial(logp, 0, [["k"], ["a"]], {1: ["k", "a"]})
        self.assertEqual(split["skipped_words"], [0, 1])
        self.assertEqual(len(split["units"]), 2)

    def test_silence_and_incomplete_words_stay_unplaced(self):
        silence = align_partial(posterior([0] * 20), 0, [["a"]], {1: ["a"]})
        self.assertFalse(silence["units"][0]["placed"])
        incomplete = align_partial(
            posterior([0] * 3 + [1] * 5 + [0] * 3), 0, [["a", "b"]], {1: ["a"]}
        )
        self.assertFalse(incomplete["units"][0]["placed"])

    def test_only_complete_source_words_are_skipped_and_metadata_is_validated(self):
        with self.assertRaises(ValueError):
            align_partial(posterior([0, 1]), 0, [[]], {1: ["a"]})
        with self.assertRaises(ValueError):
            align_partial(posterior([0, 1]) + 1, 0, [["a"]], {1: ["a"]})
