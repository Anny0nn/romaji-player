"""Mixed-script source eligibility must not depend on an English model vocabulary."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc_lexical import unique_word_matches
from ctc_source_words import source_context


def crop(text, pieces, occurrence=0):
    raw, offset, targets = text.encode(), 0, []
    for piece in pieces:
        value = piece.encode()
        first = raw.index(value, offset)
        offset = first + len(value)
        targets.append({"raw_span": [first, offset], "expected_text": piece})
    return {"occurrence": occurrence, "raw_line": text, "targets": targets}


class OriginalSourceWords(unittest.TestCase):
    def test_japanese_is_a_barrier_but_english_neighbors_are_eligible(self):
        source, owners = source_context(
            [crop("光 sing with me", ["光", "sing", "with", "me"], 4)]
        )
        self.assertEqual(
            [w["key"] for w in source["words"]], [None, "sing", "with", "me"]
        )
        observed = {
            "words": [{"key": key, "valid": True} for key in ("sing", "with", "me")]
        }
        matched = unique_word_matches(source, observed)
        self.assertEqual([owners[i] for i in matched], [(4, 1), (4, 2), (4, 3)])
        self.assertEqual(len(source["words"]), 4)

    def test_unowned_letters_cannot_disappear_between_source_groups(self):
        source, owners = source_context([crop("sing please now", ["sing", "now"])])
        self.assertEqual(source["invalid"], {0, 1})
        self.assertEqual(owners, [(0, 0), (0, 1)])
        self.assertEqual(set(source["reasons"].values()), {"unowned_source_text"})

    def test_partial_english_word_cannot_be_split_into_false_lexical_groups(self):
        source, _ = source_context([crop("sing", ["si", "ng"])])
        self.assertEqual(source["invalid"], {0, 1})

    def test_original_spelling_owns_eligibility_instead_of_generated_romaji(self):
        unit = crop("光 now", ["光", "now"])
        unit["targets"][0]["text"] = "hikari"
        source, _ = source_context([unit])
        self.assertEqual([w["key"] for w in source["words"]], [None, "now"])
        unit["targets"][0]["expected_text"] = "火"
        with self.assertRaises(ValueError):
            source_context([unit])

    def test_duplicate_occurrences_do_not_reassign_repeated_words(self):
        unit = crop("sing now", ["sing", "now"])
        with self.assertRaises(ValueError):
            source_context([unit, unit])


if __name__ == "__main__":
    unittest.main()
