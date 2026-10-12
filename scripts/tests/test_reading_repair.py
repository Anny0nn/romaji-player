"""Offline checks of experimental proposal validation; no model/runtime import."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "reading_repair",
    Path(__file__).resolve().parents[1] / "experiment-reading-repair.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReadingRepairTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "raw_line": "青い地球にありがとう",
            "words": [{"raw_span": [6, 12], "hiragana": "ちきゅう"}],
            "transcript": "青い星にありがとう",
        }
        self.edit = {
            "raw_span": [6, 12],
            "expected_text": "地球",
            "hiragana": "ほし",
            "evidence_text": "星",
        }

    def validate(self, edit):
        return module.validate_edits(self.case, {"edits": [edit]})

    def test_exact_utf8_source_word_with_cited_transcript(self):
        self.assertEqual(self.validate(self.edit), [self.edit])

    def test_spaced_reading_remains_one_original_word(self):
        spaced = {**self.edit, "hiragana": "ほし の"}
        self.assertEqual(self.validate(spaced), [spaced])

    def test_unicode_partial_boundary_and_character_indices_fail(self):
        for span in ([7, 12], [2, 4]):
            with self.assertRaises((ValueError, UnicodeError)):
                self.validate({**self.edit, "raw_span": span})

    def test_source_rewrite_and_word_regrouping_fail(self):
        for change in (
            {"expected_text": "星"},
            {"raw_span": [0, 12], "expected_text": "青い地球"},
        ):
            with self.assertRaises(ValueError):
                self.validate({**self.edit, **change})

    def test_missing_evidence_and_silent_transcript_fail(self):
        with self.assertRaises(ValueError):
            self.validate({**self.edit, "evidence_text": "moon"})
        self.case["transcript"] = ""
        with self.assertRaises(ValueError):
            self.validate(self.edit)

    def test_romaji_translation_and_redundant_reading_fail(self):
        for reading in ("hoshi", "星", "star", "ちきゅう"):
            with self.assertRaises(ValueError):
                self.validate({**self.edit, "hiragana": reading})

    def test_duplicate_edits_fail(self):
        with self.assertRaises(ValueError):
            module.validate_edits(self.case, {"edits": [self.edit, self.edit]})

    def test_empty_proposal_is_valid_and_malformed_shape_fails(self):
        self.assertEqual(module.validate_edits(self.case, {"edits": []}), [])
        for value in ({}, [], {"edits": "bad"}):
            with self.assertRaises(TypeError):
                module.validate_edits(self.case, value)

    def test_reasoning_must_finish_before_final_json_is_accepted(self):
        self.assertEqual(
            module.answer_text('<think>reason</think>{"edits":[]}', True),
            '{"edits":[]}',
        )
        with self.assertRaises(ValueError):
            module.answer_text('<think>{"edits":[]}', True)


class GroundedMappingTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "raw_line": "青い地球にありがとう",
            "transcript": "青い星にありがとう",
            "words": [
                {"raw_span": [0, 6], "expected_text": "青い", "hiragana": "あおい"},
                {"raw_span": [6, 12], "expected_text": "地球", "hiragana": "ちきゅう"},
                {"raw_span": [12, 15], "expected_text": "に", "hiragana": "に"},
                {
                    "raw_span": [15, 30],
                    "expected_text": "ありがとう",
                    "hiragana": "ありがとう",
                },
            ],
            "transcript_words": [
                {"expected_text": "青い", "hiragana": "あおい"},
                {"expected_text": "星", "hiragana": "ほし"},
                {"expected_text": "に", "hiragana": "に"},
                {"expected_text": "ありがとう", "hiragana": "ありがとう"},
            ],
        }

    def test_reading_is_derived_from_converter_not_model_text(self):
        result = module.derive_mapped_edits(
            self.case, {"matches": [[1, 1]], "hiragana": "すい"}
        )
        self.assertEqual(result[0]["hiragana"], "ほし")
        self.assertEqual(result[0]["raw_span"], [6, 12])
        self.assertEqual(result[0]["evidence_text"], "星")

    def test_unchanged_pairs_never_become_edits(self):
        result = module.derive_mapped_edits(
            self.case, {"matches": [[0, 0], [1, 1], [2, 2], [3, 3]]}
        )
        self.assertEqual(len(result), 1)
        self.case["words"][1]["hiragana"] = "ほし"
        self.assertEqual(
            module.derive_mapped_edits(self.case, {"matches": [[1, 1]]}), []
        )

    def test_mismatched_surroundings_and_multiple_changes_are_withheld(self):
        self.case["transcript_words"][0]["hiragana"] = "ちがう"
        self.assertEqual(
            module.derive_mapped_edits(self.case, {"matches": [[1, 1]]}), []
        )

    def test_empty_and_different_grouping_are_withheld(self):
        self.case["transcript_words"] = []
        self.assertEqual(module.derive_mapped_edits(self.case, {"matches": []}), [])

    def test_reordered_duplicate_and_invalid_indices_fail(self):
        for pairs in (
            [[1, 2]],
            [[1, 1], [1, 1]],
            [[-1, -1]],
            [[True, True]],
            [[99, 99]],
        ):
            with self.assertRaises((ValueError, TypeError)):
                module.derive_mapped_edits(self.case, {"matches": pairs})

    def test_edge_change_has_insufficient_context(self):
        self.case["words"][1]["hiragana"] = "ほし"
        self.case["words"][0]["hiragana"] = "あお"
        self.assertEqual(
            module.derive_mapped_edits(self.case, {"matches": [[0, 0]]}), []
        )


if __name__ == "__main__":
    unittest.main()
