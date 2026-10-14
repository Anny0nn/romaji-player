"""Offline evidence and selection checks; do not load models or commercial recordings."""

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "lyric_ensemble",
    Path(__file__).resolve().parents[1] / "experiment-lyric-ensemble.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "asr_models": [],
            "unsupported_words": 0,
            "ctc_log_probability": -30,
            "timed_words": 3,
            "total_words": 4,
            "rms": 0.1,
        }
        self.candidate = {
            **self.baseline,
            "asr_models": ["whisper", "qwen"],
            "ctc_log_probability": -20,
            "timed_words": 4,
        }

    def choose(self, change=None):
        candidate = {**self.candidate, **(change or {})}
        return module.choose_candidate([self.baseline, candidate])

    def test_two_independent_models_and_acoustic_gain_can_select_candidate(self):
        self.assertEqual(self.choose(), self.candidate)

    def test_full_coverage_alone_cannot_replace_lyrics(self):
        self.assertIs(self.choose({"ctc_log_probability": -29}), self.baseline)

    def test_extra_adjacent_words_cannot_inflate_the_coverage_denominator(self):
        self.assertIs(self.choose({"timed_words": 5, "total_words": 5}), self.baseline)

    def test_single_or_duplicate_model_votes_do_not_count_as_consensus(self):
        for models in (["whisper"], ["whisper", "whisper"], []):
            self.assertIs(self.choose({"asr_models": models}), self.baseline)

    def test_silence_unsupported_words_and_lower_coverage_are_withheld(self):
        for change in (
            {"rms": 0},
            {"unsupported_words": 1},
            {"timed_words": 2},
            {"total_words": 8},
        ):
            self.assertIs(self.choose(change), self.baseline)

    def test_missing_or_nonfinite_scores_never_win(self):
        for score in (None, float("nan"), float("inf"), -float("inf")):
            self.assertIs(self.choose({"ctc_log_probability": score}), self.baseline)
            self.baseline["ctc_log_probability"] = score
            self.assertIs(self.choose(), self.baseline)
            self.baseline["ctc_log_probability"] = -30


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "id": "track:0",
            "pcm": "private.pcm",
            "audio_sha256": "recording-sha",
            "snapshot": "source-sha",
            "start_ms": 1000,
            "end_ms": 4000,
        }

    def test_audio_recording_snapshot_and_crop_must_all_match(self):
        module.same_evidence(self.case, dict(self.case))
        for key in ("pcm", "audio_sha256", "snapshot", "start_ms", "end_ms"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.same_evidence(self.case, {**self.case, key: "changed"})

    def test_duplicate_case_cannot_silently_overwrite_evidence(self):
        with self.assertRaises(ValueError):
            module.evidence_by_id([self.case, dict(self.case)])

    def test_recording_bytes_are_checked_not_only_declared_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            pcm = Path(folder) / "audio.pcm"
            pcm.write_bytes(b"synthetic recording")
            case = {
                **self.case,
                "pcm": str(pcm),
                "audio_sha256": hashlib.sha256(pcm.read_bytes()).hexdigest(),
            }
            module.verify_recordings([case, dict(case)])
            pcm.write_bytes(b"different recording")
            with self.assertRaises(ValueError):
                module.verify_recordings([case])

    def test_unknown_reading_remains_in_timing_denominator(self):
        word = {
            "raw_span": [0, 3],
            "expected_text": "謎",
            "hiragana": "？",
            "romaji": "？",
        }
        targets = module.alignment_targets([word])
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["text"], "謎")

    def test_missing_kana_cannot_drop_an_anchored_word_from_the_denominator(self):
        value = {
            "romaji": "?",
            "hiragana": "？",
            "words": [
                {
                    "raw_span": [0, 3],
                    "expected_text": "謎",
                    "output_span": [0, 1],
                    "hiragana_span": None,
                }
            ],
        }
        words = module.converted_words(value)
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0]["hiragana"], "？")
        self.assertEqual(words[0]["raw_span"], [0, 3])

    def test_an_unmapped_lexical_word_fails_instead_of_inflating_coverage(self):
        value = {
            "romaji": "word",
            "hiragana": "word",
            "words": [
                {
                    "raw_span": None,
                    "expected_text": None,
                    "output_span": [0, 4],
                    "hiragana_span": [0, 4],
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "denominator incomplete"):
            module.converted_words(value)

    def test_ctc_labels_preserve_word_separators_and_reject_unknown_words(self):
        vocab = {"a": 1, "b": 2, "|": 0}
        self.assertEqual(
            module.ctc_labels([{"romaji": "A"}, {"romaji": "b"}], vocab),
            [1, 0, 2],
        )
        self.assertIsNone(module.ctc_labels([{"romaji": "？"}], vocab))
        self.assertIsNone(module.ctc_labels([{"romaji": "a謎b"}], vocab))
        self.assertIsNone(module.ctc_labels([], vocab))

    def test_same_time_and_unsorted_cues_use_the_next_strictly_later_time(self):
        lines = [{"start_ms": time} for time in (6000, 2000, 2000, None, 4000)]
        self.assertEqual(module.cue_crop(lines[1], lines, 250, 10000), (1750, 4550))
        self.assertEqual(module.cue_crop(lines[2], lines, 250, 10000), (1750, 4550))
        self.assertEqual(module.cue_crop(lines[0], lines, 0, 10000), (5500, 10000))

    def test_uncued_lines_fail_explicitly_instead_of_fabricating_or_dropping_targets(
        self,
    ):
        with self.assertRaisesRegex(ValueError, "Untimed lyric source"):
            module.cue_crop({"start_ms": None}, [], 0, 10000)
        with self.assertRaisesRegex(ValueError, "Invalid source cue"):
            module.cue_crop({"start_ms": 12000}, [], 0, 10000)


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.request = {
            "protocol_version": 2,
            "request_id": 1,
            "track_id": "synthetic",
            "snapshot_id": "experiment",
            "occurrence_id": 2,
            "override_revision": 0,
            "expected_conversion_signature": "signature",
        }
        self.response = {
            **{
                k: v
                for k, v in self.request.items()
                if k != "expected_conversion_signature"
            },
            "conversion_signature": "signature",
        }

    def run_response(self, responses):
        process = subprocess.CompletedProcess(
            [], 0, "\n".join(json.dumps(r) for r in responses), ""
        )
        with patch.object(module.subprocess, "run", return_value=process):
            return module.conversion_requests([self.request], Path("helper"))

    def test_converter_response_identity_is_checked_before_using_spans(self):
        self.assertEqual(self.run_response([self.response]), [self.response])
        for key in self.response:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_response([{**self.response, key: "changed"}])

    def test_missing_or_extra_converter_response_fails(self):
        for responses in ([], [self.response, self.response]):
            with self.assertRaises(ValueError):
                self.run_response(responses)


if __name__ == "__main__":
    unittest.main()
