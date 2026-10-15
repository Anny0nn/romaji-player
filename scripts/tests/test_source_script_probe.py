import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_script_probe import source_targets


class SourceScriptProbe(unittest.TestCase):
    def test_ambiguous_kanji_retains_source_and_separate_selected_reading(self):
        targets = [
            {"raw_span": [0, 6], "text": "あんや", "romaji": "an'ya"},
            {"raw_span": [6, 9], "text": "へ", "romaji": "e"},
        ]
        source = source_targets("闇夜へ", targets, "source")
        selected = source_targets("闇夜へ", targets, "selected-reading")
        self.assertEqual([u["text"] for u in source], ["闇夜", "へ"])
        self.assertEqual([u["text"] for u in selected], ["あんや", "へ"])
        self.assertEqual(source[0]["raw_span"], targets[0]["raw_span"])
        self.assertEqual(targets[0]["text"], "あんや")

    def test_punctuation_and_repeats_are_not_deleted_or_merged(self):
        source = source_targets(
            "空・空",
            [
                {"raw_span": [0, 6], "text": "そら"},
                {"raw_span": [6, 9], "text": "そら"},
            ],
            "source",
        )
        self.assertEqual([u["text"] for u in source], ["空・", "空"])
        self.assertIsNone(
            source_targets("blue sky", [{"raw_span": [0, 8], "text": "x"}], "source")
        )
        with self.assertRaises(ValueError):
            source_targets("空", [{"raw_span": [0, 2], "text": "x"}], "source")
        with self.assertRaises(ValueError):
            source_targets("abc", [{"raw_span": [2, 1], "text": "x"}], "source")
