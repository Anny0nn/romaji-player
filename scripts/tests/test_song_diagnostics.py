"""Reject stale or regrouped evidence rather than inventing missing-word counts."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "diagnose_suite", Path(__file__).resolve().parents[1] / "diagnose-song-suite.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "id": "song:0",
            "track": "song",
            "occurrence": 0,
            "pcm": "private.pcm",
            "audio_sha256": "audio",
            "snapshot": "original",
            "start_ms": 0,
            "end_ms": 30000,
            "raw_line": "空 love",
            "words": [
                {"raw_span": [0, 3], "expected_text": "空"},
                {"raw_span": [4, 8], "expected_text": "love"},
            ],
        }
        self.evidence = {
            **{k: self.case[k] for k in module.IDENTITY},
            "raw_units": [
                {"raw_span": [0, 3], "reason": "retained"},
                {"raw_span": [4, 8], "reason": "token_agreement"},
            ],
        }
        self.result = {
            "track": "song",
            "base_snapshot": "original",
            "total_words": 2,
            "timed_words": 1,
            "snapshot": {
                "occurrences": [
                    {
                        "id": 0,
                        "raw_line": "空 love",
                        "fragments": [{"raw_span": [0, 3]}],
                    }
                ]
            },
        }

    def analyze(self):
        return module.analyze([self.case], [self.evidence], {"song": self.result})

    def test_missing_latin_is_not_the_same_as_unsupported_language(self):
        summary, ledger = self.analyze()
        self.assertEqual(summary["totals"]["missing_latin"], 1)
        self.assertEqual(summary["totals"]["crops_at_30s"], 1)
        self.assertEqual(
            summary["historical_mix_reasons_for_missing"], {"token_agreement": 1}
        )
        self.assertNotIn("raw_line", ledger[0])

    def test_changed_source_audio_or_crop_cannot_be_joined(self):
        for key in module.IDENTITY:
            original = self.evidence[key]
            self.evidence[key] = "changed"
            with self.subTest(key=key), self.assertRaises((ValueError, KeyError)):
                self.analyze()
            self.evidence[key] = original
        self.result["base_snapshot"] = "different"
        with self.assertRaises(ValueError):
            self.analyze()

    def test_utf8_word_text_and_regrouped_timings_must_not_be_guessed(self):
        for change in ([1, 3], [0, 8]):
            old = self.case["words"][0]["raw_span"]
            self.case["words"][0]["raw_span"] = change
            with self.assertRaises((ValueError, UnicodeError)):
                self.analyze()
            self.case["words"][0]["raw_span"] = old
        self.result["snapshot"]["occurrences"][0]["fragments"] = [{"raw_span": [0, 8]}]
        with self.assertRaises(ValueError):
            self.analyze()

    def test_duplicate_cases_words_or_wrong_coverage_fail(self):
        with self.assertRaises(ValueError):
            module.analyze(
                [self.case, self.case], [self.evidence], {"song": self.result}
            )
        duplicate = copy.deepcopy(self.evidence)
        duplicate["raw_units"].append(duplicate["raw_units"][0])
        with self.assertRaises(ValueError):
            module.analyze([self.case], [duplicate], {"song": self.result})
        self.result["timed_words"] = 2
        with self.assertRaises(ValueError):
            self.analyze()

    def test_rust_coordinates_and_delay_are_not_rederived(self):
        case = {**self.case, "start_ms": 1250, "end_ms": 21250}
        crop = {
            "occurrence": 0,
            "start_sample": 4000,
            "end_sample": 324000,
            "lyric_origin_ms": 1000,
            "raw_line": case["raw_line"],
            "targets": [{"raw_span": w["raw_span"]} for w in case["words"]],
            "conversion_signature": "converted",
        }
        manifest = {
            "schema_version": 1,
            "producer": "Rust crop_targets",
            "sample_rate": 16000,
            "track": "song",
            "recording_origin_ms": 1000,
            "recording_samples": 400000,
            "mono_pcm_sha256": "audio",
            "snapshot": "original",
            "delay_ms": 250,
            "crops": [crop],
        }
        joined = module.attach_rust_crops([case], [manifest])
        self.assertEqual(joined[0]["rust_crop_samples"], [4000, 324000])
        for key, value in (
            ("lyric_origin_ms", 1250),
            ("start_sample", 0),
            ("conversion_signature", ""),
        ):
            changed = copy.deepcopy(manifest)
            changed["crops"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.attach_rust_crops([case], [changed])

    def test_ledger_is_private_outside_checkout_and_never_overwrites(self):
        with self.assertRaises(ValueError):
            module.private_output(module.ROOT / "ignored-diagnostics")
        with tempfile.TemporaryDirectory() as directory:
            output = module.private_output(Path(directory) / "results")
            module.write_private(output / "ledger.jsonl", [{"raw_span": [0, 3]}], True)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "ledger.jsonl").stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                json.loads((output / "ledger.jsonl").read_text())["raw_span"], [0, 3]
            )
            with self.assertRaises(FileExistsError):
                module.write_private(output / "ledger.jsonl", [])
