"""A compatibility receipt cannot hide changed source groups or selected readings."""

import copy
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "check-reading-representations.py"
spec = importlib.util.spec_from_file_location("reading_representations", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CompatibilityTests(unittest.TestCase):
    def fixture(self):
        return {
            "protocol_version": 1,
            "conversion_signature": "old",
            "romaji": "yukou",
            "hiragana": "ゆこう",
            "words": [
                {
                    "raw_span": [0, 9],
                    "expected_text": "行こう",
                    "output_span": [0, 5],
                    "hiragana_span": [0, 9],
                }
            ],
        }

    def test_only_versioned_additions_are_ignored(self):
        before = self.fixture()
        after = copy.deepcopy(before)
        after.update(
            protocol_version=2,
            conversion_signature="new",
            katakana="ユコウ",
            representation="source-reading-v1",
        )
        after["words"][0].update(katakana_span=[0, 9], reading={"written": "ゆこう"})
        self.assertTrue(module.compatible(before, after))
        for change in [
            {"raw_span": [0, 6]},
            {"expected_text": "行こ"},
            {"output_span": [0, 4]},
        ]:
            damaged = copy.deepcopy(after)
            damaged["words"][0].update(change)
            self.assertFalse(module.compatible(before, damaged))
        after["hiragana"] = "いこう"
        self.assertFalse(module.compatible(before, after))
