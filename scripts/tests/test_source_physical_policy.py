import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_physical_policy import (
    CTCLexicalEvidence,
    SavedWord,
    SourceContext,
    WordEvidence,
    WordObservation,
    WordOwner,
    overlay_candidates,
    owner_for,
    qualify_context,
    qualify_word,
    validate_context,
)


def context(count=3):
    return SourceContext(
        "source-fixture",
        "audio-fixture",
        " ".join("abcde"[:count]),
        tuple((i * 2, i * 2 + 1) for i in range(count)),
        1000,
    )


def evidence(ctx, index=0, start=100, end=300):
    owner = owner_for(ctx, index)
    return WordEvidence(
        CTCLexicalEvidence(owner, 1, 1, 0.45),
        WordObservation(owner, "tifa", start, end),
        WordObservation(owner, "native_qwen", start + 10, end + 10),
    )


def words(ctx):
    return [evidence(ctx, i, 100 + i * 200, 280 + i * 200) for i in range(3)]


class SourcePhysicalPolicyTests(unittest.TestCase):
    def test_sustained_interval_uses_measured_tifa_not_ctc_spike_duration(self):
        ctx = context()
        word = evidence(ctx, start=100, end=800)
        selected = qualify_word(ctx, word)
        self.assertIs(selected, word.tifa)
        self.assertEqual((selected.start_ms, selected.end_ms), (100, 800))
        self.assertFalse(hasattr(word.lexical, "start_ms"))
        self.assertFalse(hasattr(word.lexical, "end_ms"))

    def test_end_disagreement_withholds_even_with_matching_start(self):
        ctx = context()
        word = evidence(ctx, start=100, end=800)
        word = replace(word, native_qwen=replace(word.native_qwen, end_ms=500))
        self.assertIsNone(qualify_word(ctx, word))

    def test_exact_endpoint_tolerance_and_probability_boundary(self):
        ctx = context()
        word = evidence(ctx, start=100, end=400)
        word = replace(
            word, native_qwen=replace(word.native_qwen, start_ms=250, end_ms=550)
        )
        self.assertIs(qualify_word(ctx, word), word.tifa)
        self.assertIsNone(
            qualify_word(
                ctx,
                replace(word, native_qwen=replace(word.native_qwen, end_ms=551)),
            )
        )
        self.assertIsNone(
            qualify_word(
                ctx,
                replace(
                    word,
                    lexical=replace(word.lexical, mean_ctc_emission_probability=0.4499),
                ),
            )
        )

    def test_mixed_family_source_ownership_is_withheld(self):
        ctx = context()
        word = evidence(ctx)
        for owner in (
            replace(word.native_qwen.owner, source_id="another-source"),
            replace(word.native_qwen.owner, audio_id="another-crop"),
            replace(word.native_qwen.owner, raw_span=(2, 3)),
            replace(word.native_qwen.owner, group_index=1),
        ):
            with self.subTest(owner=owner):
                self.assertIsNone(
                    qualify_word(
                        ctx,
                        replace(
                            word, native_qwen=replace(word.native_qwen, owner=owner)
                        ),
                    )
                )
        self.assertIsNone(
            qualify_word(
                ctx, replace(word, native_qwen=replace(word.native_qwen, family="hfa"))
            )
        )

    def test_cut_edges_and_eighty_ms_minimum_apply_to_both_models(self):
        ctx = context()
        word = evidence(ctx, start=100, end=180)
        self.assertIsNotNone(qualify_word(ctx, word))
        for model in ("tifa", "native_qwen"):
            for first, last in ((0, 180), (100, 1000), (100, 179), (-1, -1)):
                bad = replace(getattr(word, model), start_ms=first, end_ms=last)
                self.assertIsNone(qualify_word(ctx, replace(word, **{model: bad})))

    def test_invalid_statistics_and_clocks_fail_closed(self):
        ctx = context()
        word = evidence(ctx)
        for field in ("union_margin_nats", "blank_margin_nats"):
            for value in (None, True, float("nan"), float("inf"), 0, -1):
                self.assertIsNone(
                    qualify_word(
                        ctx,
                        replace(word, lexical=replace(word.lexical, **{field: value})),
                    )
                )
        for value in (None, True, float("nan"), float("inf"), -1, 1.01):
            self.assertIsNone(
                qualify_word(
                    ctx,
                    replace(
                        word,
                        lexical=replace(
                            word.lexical, mean_ctc_emission_probability=value
                        ),
                    ),
                )
            )
        self.assertIsNone(
            qualify_word(ctx, replace(word, lexical=replace(word.lexical, eligible=1)))
        )
        self.assertIsNone(
            qualify_word(ctx, replace(word, tifa=replace(word.tifa, start_ms=True)))
        )

    def test_single_common_word_cannot_qualify_context(self):
        ctx = context(5)
        self.assertEqual(
            qualify_context(ctx, [evidence(ctx), None, None, None, None]), (None,) * 5
        )
        single = context(1)
        self.assertIsNotNone(qualify_word(single, evidence(single)))
        self.assertEqual(qualify_context(single, [evidence(single)]), (None,))

    def test_unsupported_original_groups_remain_in_denominator(self):
        ctx = context(5)
        records = [evidence(ctx, i) if i < 2 else None for i in range(5)]
        self.assertEqual(qualify_context(ctx, records), (None,) * 5)
        records[2] = evidence(ctx, 2)
        self.assertEqual(sum(w is not None for w in qualify_context(ctx, records)), 3)
        with self.assertRaisesRegex(ValueError, "denominator"):
            qualify_context(ctx, records[:3])

    def test_exact_half_of_four_original_groups_qualifies(self):
        ctx = context(4)
        selected = qualify_context(
            ctx, [evidence(ctx, 0), evidence(ctx, 1), None, None]
        )
        self.assertEqual(sum(w is not None for w in selected), 2)

    def test_context_requires_exact_original_slots_and_utf8_coverage(self):
        ctx = context()
        with self.assertRaisesRegex(ValueError, "ownership"):
            qualify_context(ctx, [evidence(ctx, 1), evidence(ctx, 1), None])
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_context(replace(ctx, group_spans=((0, 1), (4, 5))))
        japanese = SourceContext("s", "a", "日月", ((0, 3), (3, 6)), 1000)
        validate_context(japanese)
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            validate_context(replace(japanese, group_spans=((0, 2), (2, 6))))
        with self.assertRaises(ValueError):
            validate_context(replace(ctx, duration_ms=float("nan")))
        with self.assertRaises(ValueError):
            owner_for(ctx, True)

    def test_overlay_preserves_existing_and_protected_clocks(self):
        ctx = context()
        records = words(ctx)
        baseline = [SavedWord(owner_for(ctx, i)) for i in range(3)]
        baseline[0] = replace(baseline[0], start_ms=80, end_ms=290, protected=True)
        baseline[2] = replace(baseline[2], start_ms=700, end_ms=800, protected=True)
        before = list(baseline)
        selected = overlay_candidates(ctx, baseline, records)
        self.assertIsNone(selected[0])
        self.assertIs(selected[1], records[1].tifa)
        self.assertIsNone(selected[2])
        self.assertEqual(baseline, before)

    def test_overlay_withholds_overlap_without_trimming(self):
        ctx = context()
        records = words(ctx)
        baseline = [SavedWord(owner_for(ctx, i)) for i in range(3)]
        baseline[0] = replace(baseline[0], start_ms=80, end_ms=350, protected=True)
        self.assertIsNone(overlay_candidates(ctx, baseline, records)[1])
        self.assertEqual(records[1].tifa.start_ms, 300)

    def test_overlay_rejects_missing_baseline_group_and_wrong_owner(self):
        ctx = context()
        baseline = [SavedWord(owner_for(ctx, i)) for i in range(3)]
        with self.assertRaisesRegex(ValueError, "denominator"):
            overlay_candidates(ctx, baseline[:2], words(ctx))
        baseline[0] = replace(baseline[0], owner=WordOwner("s", "a", 0, (0, 1)))
        with self.assertRaisesRegex(ValueError, "ownership"):
            overlay_candidates(ctx, baseline, words(ctx))

    def test_unanchored_overlay_keeps_existing_seventy_percent_requirement(self):
        ctx = context(5)
        records = [evidence(ctx, i, 100 + i * 200, 280 + i * 200) for i in range(3)] + [
            None,
            None,
        ]
        baseline = [SavedWord(owner_for(ctx, i)) for i in range(5)]
        self.assertEqual(overlay_candidates(ctx, baseline, records), (None,) * 5)
        baseline[4] = replace(baseline[4], start_ms=850, end_ms=950, protected=True)
        self.assertEqual(
            sum(w is not None for w in overlay_candidates(ctx, baseline, records)), 3
        )

    def test_malformed_context_observation_and_partial_saved_clock_rejected(self):
        ctx = context()
        records = words(ctx)
        with self.assertRaisesRegex(ValueError, "ownership"):
            qualify_context(ctx, [replace(records[0], lexical={}), *records[1:]])
        baseline = [SavedWord(owner_for(ctx, i)) for i in range(3)]
        baseline[0] = replace(baseline[0], start_ms=100)
        with self.assertRaisesRegex(ValueError, "clock"):
            overlay_candidates(ctx, baseline, records)


if __name__ == "__main__":
    unittest.main()
