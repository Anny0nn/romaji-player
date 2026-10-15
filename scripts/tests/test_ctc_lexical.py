"""The presence of an unsupported group must not enable English matching."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc_lexical import unique_word_matches


def source(*keys, invalid=()):
    return {"words": [{"key": key} for key in keys], "invalid": set(invalid)}


def observed(*keys):
    return {
        "words": [
            {"key": key, "valid": True, "tokens": [i]} for i, key in enumerate(keys)
        ]
    }


class CtcSourceOwnership(unittest.TestCase):
    def test_fully_valid_english_context_is_matched(self):
        original = source("sing", "with", "me")
        decoded = observed("sing", "with", "me")
        before = copy.deepcopy((original, decoded))
        matches = unique_word_matches(original, decoded)
        self.assertEqual(set(matches), {0, 1, 2})
        self.assertIs(matches[1], decoded["words"][1])
        self.assertEqual((original, decoded), before)

    def test_unsupported_source_stays_a_barrier_without_dropping_valid_neighbors(self):
        original = source("sing", "unsupported", "with", "me", invalid={1})
        self.assertEqual(
            set(unique_word_matches(original, observed("sing", "with", "me"))), {2, 3}
        )
        self.assertEqual(
            unique_word_matches(source("sing", None, "me"), observed("sing", "me")),
            {},
        )

    def test_bpe_crossing_two_observed_words_cannot_supply_word_evidence(self):
        decoded = observed("sing", "with")
        for word in decoded["words"]:
            word.update(valid=False, tokens=[0])
        self.assertEqual(unique_word_matches(source("sing", "with"), decoded), {})

    def test_repeated_blocks_require_unique_complete_context(self):
        repeated = source("sing", "now", "sing", "now")
        self.assertEqual(unique_word_matches(repeated, observed("sing", "now")), {})
        self.assertEqual(
            set(unique_word_matches(repeated, observed("sing", "now", "sing", "now"))),
            {0, 1, 2, 3},
        )
        self.assertEqual(
            unique_word_matches(
                source("sing", "now"), observed("sing", "now", "sing", "now")
            ),
            {},
        )

    def test_invalid_owner_cannot_be_interpreted_as_a_valid_word(self):
        for invalid in ({True}, {-1}, {2}):
            with self.assertRaises(ValueError):
                unique_word_matches(
                    source("sing", "now", invalid=invalid), observed("sing", "now")
                )


if __name__ == "__main__":
    unittest.main()
