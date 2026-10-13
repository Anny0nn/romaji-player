"""Joint inference namespaces must preserve original UTF-8/repeat ownership."""

import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "context_cases", Path(__file__).resolve().parents[1] / "build-context-cases.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.cases = [
            {
                "id": f"song:{i}",
                "track": "song",
                "snapshot": "original",
                "occurrence": i,
                "pcm": "mix",
                "audio_sha256": "mixsha",
                "start_ms": 1000 + i * 1000,
                "end_ms": 2100 + i * 1000,
                "raw_line": "空",
                "words": [
                    {
                        "raw_span": [0, 3],
                        "expected_text": "空",
                        "hiragana": "そら",
                        "romaji": "sora",
                    }
                ],
            }
            for i in range(2)
        ]
        self.stems = [
            {
                **c,
                "pcm": "vocals",
                "audio_sha256": "stemsha",
                "mix_pcm": "mix",
                "mix_sha256": "mixsha",
            }
            for c in self.cases
        ]
        self.rust = {
            "schema_version": 1,
            "producer": "Rust crop_targets",
            "sample_rate": 16000,
            "track": "song",
            "snapshot": "original",
            "mono_pcm_sha256": "mixsha",
            "recording_samples": 64000,
            "recording_origin_ms": 0,
            "delay_ms": 250,
            "crops": [
                {
                    "occurrence": i,
                    "raw_line": "空",
                    "start_sample": c["start_ms"] * 16,
                    "end_sample": c["end_ms"] * 16,
                    "lyric_origin_ms": c["start_ms"] - 250,
                    "conversion_signature": "canonical",
                    "targets": [{"raw_span": [0, 3], "text": "そら", "romaji": "sora"}],
                }
                for i, c in enumerate(self.cases)
            ],
        }
        self.results = {
            "song": {
                "track": "song",
                "base_snapshot": "original",
                "snapshot": {
                    "source": {},
                    "occurrences": [
                        {"id": i, "raw_line": "空", "fragments": []} for i in range(2)
                    ],
                },
            }
        }

    def build(self):
        return module.build(self.cases, self.stems, [self.rust], self.results)

    def test_repeated_lines_keep_occurrence_and_utf8_namespace(self):
        cases = self.build()
        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0]["raw_line"], "空\n空")
        self.assertEqual([w["raw_span"] for w in cases[0]["words"]], [[0, 3], [4, 7]])
        self.assertEqual([o["occurrence"] for o in cases[0]["owners"]], [0, 1])
        self.assertEqual([o["nominated"] for o in cases[0]["owners"]], [True, False])
        self.assertEqual(cases[0]["rust_crop_samples"], [16000, 49600])
        self.assertEqual(
            cases[0]["start_ms"], 1000
        )  # Recording clock; delay not subtracted twice.
        self.assertNotEqual(cases[0]["snapshot"], "original")

    def test_source_recording_and_saved_reading_protection(self):
        self.stems[0]["mix_sha256"] = "other"
        with self.assertRaises(ValueError):
            self.build()
        self.stems[0]["mix_sha256"] = "mixsha"
        self.results["song"]["snapshot"]["source"]["derivation"] = {
            "readings": [{"raw_line": "空"}]
        }
        self.assertEqual(self.build(), [])

    def test_latin_words_cannot_be_nominated_by_japanese_verifier(self):
        for case, stem, crop in zip(self.cases, self.stems, self.rust["crops"]):
            case["raw_line"] = stem["raw_line"] = crop["raw_line"] = "hey"
            word = {
                "raw_span": [0, 3],
                "expected_text": "hey",
                "hiragana": "hey",
                "romaji": "hey",
            }
            case["words"] = stem["words"] = [word]
            crop["targets"] = [{"raw_span": [0, 3], "text": "hey", "romaji": "hey"}]
        for line in self.results["song"]["snapshot"]["occurrences"]:
            line["raw_line"] = "hey"
        self.assertEqual(self.build(), [])

    def test_invalid_utf8_and_changed_neighbor_fail(self):
        damaged = copy.deepcopy(self.cases)
        self.cases[0]["words"][0]["raw_span"] = [1, 3]
        with self.assertRaises((ValueError, UnicodeError)):
            self.build()
        self.cases = damaged
        self.results["song"]["snapshot"]["occurrences"][1]["raw_line"] = "月"
        with self.assertRaises(ValueError):
            self.build()
