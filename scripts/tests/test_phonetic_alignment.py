"""Model-free checks of phonetic experiment evidence and CTC topology."""

import importlib.util
import math
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "phonetic", Path(__file__).resolve().parents[1] / "experiment-phonetic-alignment.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PhoneticTests(unittest.TestCase):
    def test_isolated_coincidences_do_not_authorize_repairs_to_a_wrong_line(self):
        candidates = self.units([(i * 100, i * 100 + 80) for i in range(6)])
        evidence = [{**unit, "mean_probability": 0.1} for unit in candidates]
        evidence[2]["mean_probability"] = 0.9
        self.assertFalse(module.coherent_line(candidates, evidence))
        for i in (0, 1):
            evidence[i]["mean_probability"] = 0.9
        self.assertTrue(module.coherent_line(candidates, evidence))
        self.assertFalse(module.coherent_line([], []))
        self.assertTrue(module.coherent_line(candidates[:1], evidence[:1]))
        with self.assertRaises(ValueError):
            module.coherent_line(candidates, evidence[:-1])

    def raw_fixture(self):
        units = self.units([(-1, -1)])
        candidate = {
            **units[0],
            "reason": "token_agreement",
            "start_ms": 100,
            "end_ms": 300,
            "agreement": 0.9,
            "mean_similarity": 0.5,
        }
        evidence = {**candidate, "mean_probability": 0.3}
        return {"units": units, "raw_units": [candidate]}, [evidence]

    def test_rejected_raw_word_needs_independent_endpoints_and_all_original_bounds(
        self,
    ):
        vocals, evidence = self.raw_fixture()
        result = module.supported_raw(vocals, evidence, 500)
        self.assertEqual(result[0]["start_ms"], 100)
        self.assertEqual(vocals["units"][0]["start_ms"], -1)
        for change in (
            {"agreement": 0.89},
            {"agreement": float("nan")},
            {"mean_similarity": float("inf")},
            {"end_ms": 501},
            {"end_ms": 179},
            {"reason": "incomplete"},
        ):
            trial = {**vocals, "raw_units": [{**vocals["raw_units"][0], **change}]}
            self.assertEqual(
                module.supported_raw(trial, evidence, 500), vocals["units"]
            )
        for change in ({"mean_probability": 0.29}, {"end_ms": 501}):
            self.assertEqual(
                module.supported_raw(vocals, [{**evidence[0], **change}], 500),
                vocals["units"],
            )

    def test_raw_rescue_cannot_reorder_targets_or_replace_an_existing_interval(self):
        vocals, evidence = self.raw_fixture()
        vocals["units"][0].update(start_ms=200, end_ms=400)
        self.assertEqual(module.supported_raw(vocals, evidence, 500), vocals["units"])
        vocals["raw_units"][0]["raw_span"] = [100, 200]
        with self.assertRaises(ValueError):
            module.supported_raw(vocals, evidence, 500)

    def test_wrong_verse_controls_report_an_ineligible_song_without_fake_targets(self):
        case = {
            "id": "fixture:0",
            "track": "fixture",
            "words": [
                {"hiragana": "English", "raw_span": [i, i + 1]} for i in range(5)
            ],
        }
        with patch.object(module, "print") as log:
            self.assertEqual(
                module.wrong_controls(
                    [case], [{"id": case["id"]}], [{"id": case["id"]}], False
                ),
                [],
            )
        self.assertIn("control_unavailable", log.call_args.args[0])

    def test_region_repairs_a_blocking_neighbor_only_with_independent_support(self):
        baseline = self.units([(100, 300), (-1, -1), (500, 600)])
        vocals = self.units([(100, 200), (210, 450), (500, 600)])
        phonetic = [{**u, "mean_probability": 0.9} for u in vocals]
        repaired = module.repair_regions(baseline, vocals, phonetic)
        self.assertEqual(
            repaired[:2], [{**u, "repair": "phonetic-region"} for u in vocals[:2]]
        )
        self.assertEqual(repaired[2], baseline[2])
        self.assertEqual(baseline[0]["end_ms"], 300)
        phonetic[0]["mean_probability"] = 0.1
        self.assertEqual(module.repair_regions(baseline, vocals, phonetic), baseline)

    def test_region_withholds_overlap_and_disagreeing_ends_in_any_changed_word(self):
        baseline = self.units([(100, 300), (-1, -1), (400, 600)])
        vocals = self.units([(100, 200), (210, 450), (460, 600)])
        evidence = [{**u, "mean_probability": 0.9} for u in vocals]
        repaired = module.repair_regions(baseline, vocals, evidence)
        self.assertTrue(all(u.get("repair") == "phonetic-region" for u in repaired))
        for bad in (
            {"start_ms": 1, "end_ms": 200},
            {"mean_probability": float("nan")},
            {"end_ms": 900},
        ):
            trial = [*evidence[:2], {**evidence[2], **bad}]
            self.assertEqual(module.repair_regions(baseline, vocals, trial), baseline)
        overlapping = self.units([(100, 250), (210, 450), (460, 600)])
        evidence = [{**u, "mean_probability": 0.9} for u in overlapping]
        self.assertEqual(
            module.repair_regions(baseline, overlapping, evidence), baseline
        )

    def test_region_cannot_retime_more_than_four_words_or_cross_unchanged_anchors(self):
        baseline = self.units([(0, 100), (100, 200), (200, 300), (300, 400), (-1, -1)])
        vocals = self.units([(0, 40), (40, 80), (80, 120), (120, 160), (160, 200)])
        evidence = [{**u, "mean_probability": 0.9} for u in vocals]
        self.assertEqual(module.repair_regions(baseline, vocals, evidence), baseline)

    def test_chunk_windows_preserve_original_zero_and_cover_short_and_odd_tracks(self):
        for length in (1, 3, 8, 9, 15):
            windows = list(module.chunk_windows(length, 8))
            self.assertEqual(windows[0][0], -4)
            covered = set()
            for start, first, last in windows:
                self.assertTrue(0 <= first < last <= length)
                self.assertTrue(0 <= first - start < last - start <= 8)
                covered.update(range(first, last))
            self.assertEqual(covered, set(range(length)))
        for length, size in ((0, 8), (1, 0), (1, 3)):
            with self.assertRaises(ValueError):
                list(module.chunk_windows(length, size))

    def test_phonetic_support_requires_finite_probability_and_both_boundaries(self):
        unit = {"start_ms": 100, "end_ms": 300}
        self.assertTrue(
            module.phonetic_support(unit, {**unit, "mean_probability": 0.3})
        )
        for value in (0.29, float("nan"), float("inf"), 1.1):
            self.assertFalse(
                module.phonetic_support(unit, {**unit, "mean_probability": value})
            )
        self.assertFalse(module.phonetic_support(unit, unit))
        self.assertFalse(
            module.phonetic_support(
                unit, {**unit, "mean_probability": 0.9, "end_ms": 501}
            )
        )

    def test_independent_phonetics_can_fill_a_gap_with_unstable_mix_vocal_anchors(self):
        baseline = self.units([(100, 200), (-1, -1), (500, 600)])
        vocals = self.units([(310, 400), (410, 490), (500, 600)])
        evidence = [{**u, "mean_probability": 0.9} for u in vocals]
        result = module.recover_gaps(baseline, vocals, evidence)
        self.assertEqual(result[1], vocals[1])
        evidence[1]["mean_probability"] = 0.1
        self.assertEqual(module.recover_gaps(baseline, vocals, evidence), baseline)
        with self.assertRaises(ValueError):
            module.recover_gaps(baseline, vocals, evidence[:2])

    def test_a_missing_word_cannot_hide_overlap_between_two_new_intervals(self):
        baseline = self.units([(100, 200), (-1, -1), (-1, -1), (-1, -1), (1000, 1100)])
        vocals = self.units(
            [(100, 200), (250, 650), (-1, -1), (500, 700), (1000, 1100)]
        )
        evidence = [{**unit, "mean_probability": 0.9} for unit in vocals]
        result = module.recover_gaps(baseline, vocals, evidence)
        self.assertEqual(result[1], vocals[1])
        self.assertEqual(result[3], baseline[3])

    def test_negative_controls_preserve_the_target_spans_and_private_audio_identity(
        self,
    ):
        case = {
            "id": "fixture:0",
            "track": "4cH6RfZ1qIuz6sumRoDEGK",
            "pcm": "original.pcm",
            "audio_sha256": "original",
            "words": [{"raw_span": [0, 6], "expected_text": "地球"}],
        }
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            result = module.controls([case], Path(folder))
            silent, instrumental = result[1:]
            self.assertEqual(instrumental["pcm"], case["pcm"])
            self.assertEqual(silent["words"], case["words"])
            self.assertEqual(Path(silent["pcm"]).stat().st_size, 6 * 16000 * 4)
            self.assertNotEqual(silent["audio_sha256"], case["audio_sha256"])

    def units(self, times):
        return [
            {"raw_span": [i * 3, (i + 1) * 3], "start_ms": start, "end_ms": end}
            for i, (start, end) in enumerate(times)
        ]

    def test_fallback_fills_stable_gaps_and_preserves_existing_timings(self):
        baseline = self.units([(100, 200), (-1, -1), (500, 600)])
        vocals = self.units([(110, 210), (250, 450), (510, 610)])
        result = module.recover_gaps(baseline, vocals)
        self.assertEqual(result, [baseline[0], vocals[1], baseline[2]])
        self.assertEqual(baseline[1]["start_ms"], -1)

    def test_fallback_withholds_unanchored_overlap_and_unstable_neighbors(self):
        baseline = self.units([(100, 200), (-1, -1), (500, 600)])
        for times in (
            [(100, 200), (190, 450), (500, 600)],
            [(100, 200), (250, 510), (500, 600)],
            [(310, 400), (410, 490), (500, 600)],
        ):
            self.assertEqual(module.recover_gaps(baseline, self.units(times)), baseline)
        missing = self.units([(-1, -1), (-1, -1)])
        self.assertEqual(
            module.recover_gaps(missing, self.units([(100, 200), (300, 400)])), missing
        )

    def test_fallback_rejects_changed_grouping_and_prevents_recovered_word_overlap(
        self,
    ):
        baseline = self.units([(100, 200), (-1, -1), (-1, -1), (700, 800)])
        vocals = self.units([(100, 200), (250, 500), (450, 650), (700, 800)])
        result = module.recover_gaps(baseline, vocals)
        self.assertEqual(result[1], vocals[1])
        self.assertEqual(result[2], baseline[2])
        with self.assertRaises(ValueError):
            module.recover_gaps(baseline, vocals[:3])

    def test_mms_blank_id_is_distinct_from_its_word_separator(self):
        rows = [[-10.0] * 30 for _ in range(3)]
        for row, token in zip(rows, (1, 0, 2), strict=True):
            row[token] = 0.0
        self.assertEqual(module.ctc_path(rows, [1, 0, 2], blank=29), [1, 3, 5])
        with self.assertRaises(ValueError):
            module.ctc_path(rows, [1], blank=30)

    def test_stem_result_must_match_original_audio_and_every_source_word(self):
        case = {
            "id": "fixture:0",
            "pcm": "mix.pcm",
            "audio_sha256": "original",
            "snapshot": "source",
            "start_ms": 10,
            "end_ms": 100,
            "words": [{"raw_span": [0, 3]}, {"raw_span": [3, 6]}],
        }
        result = {
            **module.identity(case),
            "pcm": "stem.pcm",
            "audio_sha256": "stem",
            "mix_pcm": "mix.pcm",
            "mix_sha256": "original",
            "units": [
                {"raw_span": [0, 3], "start_ms": 1, "end_ms": 2},
                {"raw_span": [3, 6], "start_ms": -1, "end_ms": -1},
            ],
        }
        module.validate_result(case, result)
        for change in (
            {"mix_sha256": "other"},
            {"snapshot": "other"},
            {"end_ms": 101},
            {"units": result["units"][:1]},
            {"units": result["units"][::-1]},
        ):
            with self.assertRaises(ValueError):
                module.validate_result(case, {**result, **change})

    def test_comparison_keeps_unsupported_words_and_reports_losses(self):
        case = {
            "id": "fixture:0",
            "pcm": "mix.pcm",
            "audio_sha256": "original",
            "snapshot": "source",
            "start_ms": 0,
            "end_ms": 1000,
            "words": [{"raw_span": [0, 3]}, {"raw_span": [3, 6]}],
        }
        base = {
            **module.identity(case),
            "units": [
                {"raw_span": [0, 3], "start_ms": 100, "end_ms": 200},
                {"raw_span": [3, 6], "start_ms": -1, "end_ms": -1},
            ],
        }
        trial = {
            **base,
            "units": [
                {"raw_span": w["raw_span"], "start_ms": -1, "end_ms": -1}
                for w in case["words"]
            ],
        }
        counts = module.compare([case], [base], [trial])["fixture"]
        self.assertEqual(counts["source_words"], 2)
        self.assertEqual(counts["lost_raw"], 1)
        self.assertEqual(counts["trial_retained"], 0)
        with self.assertRaises(ValueError):
            module.compare([case], [base], [])

    def test_silence_control_cannot_overwrite_a_real_song_stem(self):
        real = {"track": "same-song", "audio_sha256": "a" * 64}
        silence = {**real, "audio_sha256": "b" * 64}
        self.assertNotEqual(
            module.stem_path(Path("stems"), real),
            module.stem_path(Path("stems"), silence),
        )
        with self.assertRaises(ValueError):
            module.stem_path(Path("stems"), {**real, "audio_sha256": "../audio"})

    def rows(self, tokens):
        return [[math.log(0.98 if i == t else 0.01) for i in range(3)] for t in tokens]

    def test_repeated_kana_require_a_blank_between_ctc_labels(self):
        self.assertIsNone(module.ctc_path(self.rows([1, 1]), [1, 1]))
        path = module.ctc_path(self.rows([0, 1, 0, 1, 0]), [1, 1])
        self.assertEqual(path, [0, 1, 2, 3, 4])

    def test_different_kana_can_follow_without_a_blank(self):
        self.assertEqual(module.ctc_path(self.rows([1, 2]), [1, 2]), [1, 3])

    def test_empty_and_impossible_targets_never_get_fabricated_times(self):
        for rows, labels in (
            ([], [1]),
            (self.rows([1]), []),
            (self.rows([1]), [1, 2]),
            (self.rows([0]), [0]),
        ):
            self.assertIsNone(module.ctc_path(rows, labels))

    def test_bad_or_nonfinite_posteriors_are_rejected(self):
        for rows, labels in (
            ([[0]], [2]),
            ([[0, 0], [0]], [1]),
            ([[0, float("nan")]], [1]),
        ):
            with self.assertRaises(ValueError):
                module.ctc_path(rows, labels)

    def test_boundary_agreement_checks_both_ends_and_missing_intervals(self):
        a = {"start_ms": 500, "end_ms": 1000}
        self.assertTrue(module.agree(a, {"start_ms": 700, "end_ms": 800}))
        for b in (
            {"start_ms": 500, "end_ms": 1300},
            {"start_ms": -1, "end_ms": -1},
            {"start_ms": 500, "end_ms": 500},
        ):
            self.assertFalse(module.agree(a, b))

    def test_phonetic_particles_follow_sung_pronunciation(self):
        for spelling, romaji, spoken in (
            ("は", "wa", "わ"),
            ("は", "ha", "は"),
            ("へ", "e", "え"),
            ("を", "o", "お"),
        ):
            self.assertEqual(
                module.spoken({"hiragana": spelling, "romaji": romaji}), spoken
            )

    def test_evidence_preserves_every_recording_and_source_identity_field(self):
        case = {
            "id": "fixture:0",
            "pcm": "private.pcm",
            "audio_sha256": "audio",
            "snapshot": "source",
            "start_ms": 10,
            "end_ms": 100,
            "raw_line": "private",
        }
        self.assertEqual(set(module.identity(case)), set(case) - {"raw_line"})
        module.ensemble.same_evidence(case, module.identity(case))


if __name__ == "__main__":
    unittest.main()
