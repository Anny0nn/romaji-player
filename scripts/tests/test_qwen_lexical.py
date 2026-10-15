"""No forced confidence, split BPE word scores, or ambiguous repeat ownership."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qwen_lexical import (
    context_matches,
    decoder_words,
    exact_matches,
    recognition_words,
    recover_recognized_pairs,
    recover_recognized_views,
)


class Tokenizer:
    all_special_ids = (99,)

    def __init__(self, pieces):
        self.pieces = pieces

    def decode(self, ids, **_kwargs):
        return b"".join(
            self.pieces[i] for i in ids if i not in self.all_special_ids
        ).decode(errors="replace")


class QwenLexical(unittest.TestCase):
    def observed(self, text):
        return [
            {
                "word": word,
                "probability": 0.9,
                "confidence_kind": "qwen-free-decoder-geometric-mean",
                "source_conditioned": False,
            }
            for word in text.split()
        ]

    def test_context_exposes_neighboring_repeats_before_assigning_occurrence(self):
        cue = {
            "occurrence": 9,
            "raw_line": "blue sky",
            "targets": [
                {"raw_span": [0, 4], "text": "blue"},
                {"raw_span": [5, 8], "text": "sky"},
            ],
        }
        matched = context_matches(
            [cue, {**cue, "occurrence": 11}], self.observed("blue sky")
        )
        self.assertEqual(set(matched), {9, 11})
        self.assertFalse(
            any(u["source_match"] for row in matched.values() for u in row)
        )

    def test_context_preserves_line_local_unicode_spans_and_original_spelling(self):
        cues = [
            {
                "occurrence": 9,
                "raw_line": "青 blue sky",
                "targets": [
                    {"raw_span": [0, 3], "text": "青"},
                    {"raw_span": [4, 8], "text": "untrusted"},
                    {"raw_span": [9, 12], "text": "sky"},
                ],
            },
            {
                "occurrence": 11,
                "raw_line": "stars shine",
                "targets": [
                    {"raw_span": [0, 5], "text": "stars"},
                    {"raw_span": [6, 11], "text": "shine"},
                ],
            },
        ]
        matched = context_matches(cues, self.observed("blue sky stars shine"))
        self.assertEqual([u["source_match"] for u in matched[9]], [False, True, True])
        self.assertTrue(all(u["source_match"] for u in matched[11]))
        self.assertEqual([u["raw_span"] for u in matched[9]], [[0, 3], [4, 8], [9, 12]])
        with self.assertRaises(ValueError):
            context_matches([cues[0], cues[0]], [])
        with self.assertRaises(ValueError):
            context_matches([{**cues[0], "targets": [{"raw_span": [1, 3]}]}], [])

    def test_free_word_scores_exclude_language_prefix_and_special_tokens(self):
        tokenizer = Tokenizer(
            [b"language English<asr_text>", b" ca", b"n't", b" wait", b" now"]
        )
        words = decoder_words(
            tokenizer,
            [0, 1, 2, 3, 4, 99],
            [math.log(p) for p in [0.1, 0.9, 0.4, 0.8, 0.9, 0.1]],
            "can't wait now",
        )
        self.assertAlmostEqual(words[0]["probability"], 0.6)
        self.assertEqual(words[0]["decoder_token_indices"], [1, 2])
        self.assertAlmostEqual(words[1]["probability"], 0.8)
        self.assertFalse(words[0]["source_conditioned"])

    def test_repetition_cleaned_transcript_withholds_only_that_complete_view(self):
        tokenizer = Tokenizer(
            [b"language English<asr_text>", b"blue sky ", b"blue sky"]
        )
        row = {
            "budget_exhausted": False,
            "decoded": {"language": "English", "transcription": "blue sky"},
            "decoded_tokens": [0, 1, 2],
            "token_log_probabilities": [-0.01, -0.01, -0.01],
        }
        words, reason = recognition_words(tokenizer, row, "auto")
        self.assertEqual((words, reason), ([], "unreconstructible_transcript"))
        row["decoded_tokens"] = [0, 2]
        row["token_log_probabilities"] = [-0.01, -0.01]
        self.assertIsNone(recognition_words(tokenizer, row, "auto")[1])
        row["token_log_probabilities"] = [math.nan, -0.01]
        # Corrupt acoustic records are errors, not ordinary view abstentions.
        with self.assertRaises(ValueError):
            recognition_words(tokenizer, row, "auto")

    def test_partial_unicode_bytes_merge_and_a_cross_word_token_has_no_word_score(self):
        data = "空 light".encode()
        words = decoder_words(
            Tokenizer([data[:1], data[1:3], data[3:]]),
            [0, 1, 2],
            [-0.1] * 3,
            "空 light",
        )
        self.assertEqual(words[0]["decoder_token_indices"], [0, 1])
        crossed = decoder_words(Tokenizer([b"blue sky"]), [0], [-0.1], "blue sky")
        self.assertTrue(all(w["probability"] is None for w in crossed))

    def test_unique_whole_blocks_keep_actual_confidence_and_reject_forced_or_repeats(
        self,
    ):
        targets = [
            {"raw_span": [0, 4], "text": "blue"},
            {"raw_span": [5, 8], "text": "sky"},
        ]
        words = [
            {
                "word": w,
                "probability": 0.8,
                "confidence_kind": "qwen-free-decoder-geometric-mean",
                "source_conditioned": False,
            }
            for w in ("blue", "sky")
        ]
        self.assertTrue(all(w["source_match"] for w in exact_matches(targets, words)))
        self.assertFalse(
            any(w["source_match"] for w in exact_matches(targets, words * 2))
        )
        forced = [{**w, "source_conditioned": True} for w in words]
        self.assertFalse(any(w["source_match"] for w in exact_matches(targets, forced)))
        with self.assertRaises(ValueError):
            decoder_words(Tokenizer([b"blue"]), [0], [math.nan], "blue")

    def test_recovery_keeps_original_clocks_and_requires_typed_adjacent_witnesses(self):
        baseline = [
            {"raw_span": [i * 2, i * 2 + 1], "start_ms": -1, "end_ms": -1}
            for i in range(4)
        ]
        baseline[0].update(start_ms=-30, end_ms=100, protected=True)
        clocks = [
            {**u, "start_ms": 10 + i * 200, "end_ms": 160 + i * 200}
            for i, u in enumerate(baseline)
        ]
        views = [
            [
                {
                    "raw_span": u["raw_span"],
                    "source_match": True,
                    "probability": 0.9,
                    "confidence_kind": "qwen-free-decoder-geometric-mean",
                    "source_conditioned": False,
                    "matched_words": 4,
                }
                for u in baseline
            ]
            for _ in range(2)
        ]
        recovered = recover_recognized_pairs(baseline, clocks, views, 1000, 4)
        self.assertEqual(recovered[0], baseline[0])
        self.assertEqual(recovered[1]["start_ms"], clocks[1]["start_ms"])
        self.assertTrue(all(u["start_ms"] == -1 for u in baseline[1:]))
        # Neither a forced probability nor one isolated recognized word is evidence.
        for u in views[1]:
            u["source_conditioned"] = True
        self.assertEqual(
            recover_recognized_pairs(baseline, clocks, views, 1000, 4), baseline
        )
        for u in views[1]:
            u["source_conditioned"] = False
            u["source_match"] = False
        views[1][1]["source_match"] = True
        self.assertEqual(
            recover_recognized_pairs(baseline, clocks, views, 1000, 4), baseline
        )

    def test_recovery_rejects_collisions_partial_empty_lines_and_changed_ownership(
        self,
    ):
        baseline = [
            {"raw_span": [i, i + 1], "start_ms": -1, "end_ms": -1} for i in range(4)
        ]
        clocks = [
            {**u, "start_ms": 10 + i * 200, "end_ms": 190 + i * 200}
            for i, u in enumerate(baseline)
        ]
        view = [
            {
                "raw_span": u["raw_span"],
                "source_match": i < 2,
                "probability": 0.9,
                "confidence_kind": "qwen-free-decoder-geometric-mean",
                "source_conditioned": False,
                "matched_words": 2,
            }
            for i, u in enumerate(baseline)
        ]
        self.assertEqual(
            recover_recognized_pairs(baseline, clocks, [view, view], 1000, 4), baseline
        )
        baseline[2].update(start_ms=300, end_ms=800, protected=True)
        recovered = recover_recognized_pairs(baseline, clocks, [view, view], 1000, 4)
        self.assertEqual(recovered[1], baseline[1])
        self.assertEqual(recovered[2], baseline[2])
        changed = [{**u, "raw_span": [100, 101]} for u in clocks]
        with self.assertRaises(ValueError):
            recover_recognized_pairs(baseline, changed, [view, view], 1000, 4)

    def test_third_waveform_still_requires_two_typed_witnesses_per_word(self):
        baseline = [
            {"raw_span": [i, i + 1], "start_ms": -1, "end_ms": -1} for i in range(3)
        ]
        clocks = [
            {**u, "start_ms": 10 + i * 200, "end_ms": 160 + i * 200}
            for i, u in enumerate(baseline)
        ]
        full = [
            {
                "raw_span": u["raw_span"],
                "source_match": True,
                "probability": 0.9,
                "confidence_kind": "qwen-free-decoder-geometric-mean",
                "source_conditioned": False,
                "matched_words": 3,
            }
            for u in baseline
        ]
        absent = [{**u, "source_match": False} for u in full]
        self.assertEqual(
            recover_recognized_pairs(baseline, clocks, [full, absent], 1000, 3),
            baseline,
        )
        result = recover_recognized_views(
            baseline, clocks, [full, absent, full], 1000, 3
        )
        self.assertEqual(result, clocks)
        for invalid in (
            {"source_conditioned": True},
            {"confidence_kind": "forced"},
            {"probability": 0.69},
            {"probability": math.nan},
            {"matched_words": 1},
        ):
            third = [{**u, **invalid} for u in full]
            self.assertEqual(
                recover_recognized_views(
                    baseline, clocks, [full, absent, third], 1000, 3
                ),
                baseline,
            )
        for views in ([full], [full] * 4):
            with self.assertRaises(ValueError):
                recover_recognized_views(baseline, clocks, views, 1000, 3)
        with self.assertRaises(ValueError):
            recover_recognized_pairs(baseline, clocks, [full] * 3, 1000, 3)

    def test_third_waveform_never_substitutes_a_clock_or_bypasses_protection(self):
        baseline = [
            {"raw_span": [i, i + 1], "start_ms": -1, "end_ms": -1} for i in range(3)
        ]
        baseline[0].update(start_ms=-50, end_ms=150, protected=True)
        clocks = [
            {**u, "start_ms": 10 + i * 200, "end_ms": 160 + i * 200}
            for i, u in enumerate(baseline)
        ]
        view = [
            {
                "raw_span": u["raw_span"],
                "source_match": True,
                "probability": 0.9,
                "confidence_kind": "qwen-free-decoder-geometric-mean",
                "source_conditioned": False,
                "matched_words": 3,
                "start_ms": 9999,
                "end_ms": 99999,
            }
            for u in baseline
        ]
        result = recover_recognized_views(baseline, clocks, [view] * 3, 1000, 3)
        self.assertEqual(result, [baseline[0], *clocks[1:]])
        clocks[1].update(start_ms=-1, end_ms=-1)
        self.assertEqual(
            recover_recognized_views(baseline, clocks, [view] * 3, 1000, 3),
            baseline,
        )
        changed = [{**u, "raw_span": [100, 101]} for u in view]
        with self.assertRaises(ValueError):
            recover_recognized_views(baseline, clocks, [view, view, changed], 1000, 3)
