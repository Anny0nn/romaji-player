"""Original script owns timings; conditioned confidence cannot split a word."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from whisper_source_evidence import owned_envelopes, owned_token_indices


def observed(word, start, end):
    return {"word": word, "start_ms": start, "end_ms": end, "probability": 0.9}


class SourceAttentionMapping(unittest.TestCase):
    def test_token_bytes_preserve_utf8_and_whitespace_ownership(self):
        text = "空 light"
        data = text.encode()
        self.assertEqual(
            owned_token_indices(
                text,
                [{"raw_span": [0, 3]}, {"raw_span": [4, 9]}],
                [data[:1], data[1:3], data[3:]],
            ),
            [[0, 1], [2]],
        )

    def test_spanning_bpe_is_not_assigned_to_two_source_words(self):
        self.assertEqual(
            owned_token_indices(
                "cat's", [{"raw_span": [0, 3]}, {"raw_span": [4, 5]}], [b"cat's"]
            ),
            [None, None],
        )
        with self.assertRaises(ValueError):
            owned_token_indices("cat", [{"raw_span": [0, 3]}], [b"dog"])

    def test_complete_kana_kanji_pieces_merge_to_original_group(self):
        text = "今日の光"
        targets = [{"raw_span": [0, 6]}, {"raw_span": [6, 9]}, {"raw_span": [9, 12]}]
        units = owned_envelopes(
            text,
            targets,
            [
                observed("今", 100, 200),
                observed("日", 200, 350),
                observed("の", 350, 430),
                observed("光", 500, 700),
            ],
            1000,
        )
        self.assertEqual(
            [(u["start_ms"], u["end_ms"]) for u in units],
            [(100, 350), (350, 430), (500, 700)],
        )
        self.assertTrue(all(u["source_conditioned"] for u in units))
        self.assertEqual(
            [u["raw_span"] for u in units], [t["raw_span"] for t in targets]
        )

    def test_model_word_spanning_source_groups_cannot_invent_split_clocks(self):
        units = owned_envelopes(
            "cat's",
            [{"raw_span": [0, 3]}, {"raw_span": [4, 5]}],
            [observed("cat's", 100, 400)],
            1000,
        )
        self.assertTrue(all(u["start_ms"] == -1 for u in units))

    def test_bad_reconstruction_partial_utf8_and_degenerate_observations_reject(self):
        with self.assertRaises(ValueError):
            owned_envelopes(
                "空", [{"raw_span": [0, 3]}], [observed("海", 100, 300)], 1000
            )
        with self.assertRaises(UnicodeDecodeError):
            owned_envelopes(
                "空", [{"raw_span": [0, 1]}], [observed("空", 100, 300)], 1000
            )
        for start, end in ((100, 100), (-1, 100), (900, 1100)):
            unit = owned_envelopes(
                "空", [{"raw_span": [0, 3]}], [observed("空", start, end)], 1000
            )[0]
            self.assertEqual(unit["start_ms"], -1)
            self.assertIsNone(unit["conditional_probability"])

    def test_whitespace_is_not_a_phone_or_timing_to_be_partitioned(self):
        units = owned_envelopes(
            "the light",
            [{"raw_span": [0, 3]}, {"raw_span": [4, 9]}],
            [observed("the", 100, 300), observed(" light", 320, 600)],
            1000,
        )
        self.assertEqual(units[1]["start_ms"], 320)
        self.assertEqual(units[1]["end_ms"], 600)
