import copy
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "hybrid_google_timing", SCRIPTS / "hybrid_google_timing.py"
)
hybrid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hybrid)


class HybridGoogleTests(unittest.TestCase):
    def test_candidate_line_join_preserves_source_bytes_and_punctuation(self):
        text = "  空\n月！  "
        self.assertEqual(hybrid.normalized_candidate(text), "空 月！")
        self.assertEqual(text, "  空\n月！  ")
        for invalid in ("", " \n ", "あ" * 3000, None):
            with (
                self.subTest(value_type=type(invalid).__name__),
                self.assertRaises(ValueError),
            ):
                hybrid.normalized_candidate(invalid)

    def test_existing_owner_spans_and_converter_must_match_rust_export(self):
        source = {
            "targets": [
                {
                    "raw_span": [0, 3],
                    "text": "そら",
                    "romaji": "sora",
                    "pronunciation": None,
                }
            ],
            "source_groups": 1,
            "conversion_signature": "frozen",
        }
        crop = {
            "targets": [{"raw_span": [0, 3], "text": "そら", "romaji": "sora"}],
            "source_word_count": 1,
            "conversion_signature": "frozen",
        }
        hybrid.validate_source_targets(source, crop)
        for field, value in (
            ("raw_span", [0, 2]),
            ("text", "つき"),
            ("romaji", "tsuki"),
        ):
            changed = copy.deepcopy(source)
            changed["targets"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                hybrid.validate_source_targets(changed, crop)
        for field, value in (("source_groups", 2), ("conversion_signature", "new")):
            changed = {**source, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                hybrid.validate_source_targets(changed, crop)
