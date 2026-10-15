"""Blank collapse is acoustic; special predictions cannot silently become text."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_first_ctc import greedy
from singing_letters import decode_letters


class SingingLetters(unittest.TestCase):
    def test_decoding_uses_token_ids_and_keeps_unknown_or_special_predictions(self):
        vocabulary = {
            "|": 0,
            **{chr(96 + i): i for i in range(1, 27)},
            "'": 27,
            "[UNK]": 28,
            "[PAD]": 29,
            "<s>": 30,
            "</s>": 31,
        }
        observations = []
        for label in [3, 3, 29, 1, 20, 0, 28]:
            frame = [-10.0] * 32
            frame[label] = -0.01
            observations.append(frame)
        result = greedy(observations, 29)
        self.assertEqual(result["token_ids"], [3, 1, 20, 0, 28])
        self.assertEqual(decode_letters(result["token_ids"], vocabulary), "cat [UNK]")
        self.assertEqual(result["emission_frames"][0], [0, 1])
        with self.assertRaises(ValueError):
            decode_letters([1], {"a": 1})
