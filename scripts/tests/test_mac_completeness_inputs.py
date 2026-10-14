"""Saved readings and timings keep original byte ownership across repeated lines."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mac_completeness_inputs import load_suite


class MacCompletenessInputs(unittest.TestCase):
    def fixture(self, root):
        word = {
            "raw_span": [0, 3],
            "expected_text": "歌",
            "hiragana": "うた",
            "romaji": "uta",
        }
        cases = [
            {
                "id": f"song:{i}",
                "track": "song",
                "snapshot": "source",
                "occurrence": i,
                "start_ms": i * 1000,
                "end_ms": (i + 1) * 1000,
                "raw_line": "歌",
                "words": [word],
                "pcm": "unused.pcm",
                "audio_sha256": "unused",
            }
            for i in range(2)
        ]
        document = {
            "base_snapshot": "source",
            "delay_ms": 0,
            "total_words": 2,
            "timed_words": 2,
            "snapshot": {
                "source": {
                    "derivation": {
                        "readings": [
                            {
                                "raw_line": "歌",
                                "raw_span": [0, 3],
                                "hiragana": "か",
                                "romaji": "ka",
                            }
                        ]
                    }
                },
                "occurrences": [
                    {
                        "id": i,
                        "raw_line": "歌",
                        "fragments": [
                            {
                                "raw_span": [0, 3],
                                "interval": {
                                    "start_ms": i * 1000 + 100,
                                    "end_ms": i * 1000 + 300,
                                },
                            }
                        ],
                    }
                    for i in range(2)
                ],
            },
        }
        for name, value in (
            ("mix.json", cases),
            ("kim.json", cases),
            ("saved.json", document),
        ):
            (root / name).write_text(json.dumps(value))
        path = root / "suite.json"
        path.write_text(
            json.dumps(
                {
                    "mix_cases": "mix.json",
                    "kim_cases": "kim.json",
                    "results": [{"track": "song", "path": "saved.json"}],
                }
            )
        )
        return path, document

    def test_saved_reading_is_shared_while_each_repeat_keeps_its_own_clock(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, _ = self.fixture(Path(temporary))
            _, rows, _ = load_suite(path)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["words"][0]["hiragana"], "か")
            self.assertTrue(row["words"][0]["protected_reading"])
            self.assertEqual(row["words"][0]["raw_span"], [0, 3])
            self.assertEqual(row["baseline"][0]["start_ms"], 100)
            self.assertEqual(row["baseline"][0]["end_ms"], 300)

    def test_changed_source_or_clock_is_rejected_instead_of_reattaching_timings(self):
        for change in (
            {"delay_ms": 250},
            {"base_snapshot": "changed"},
            {"total_words": 3},
        ):
            with (
                self.subTest(change=change),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                path, document = self.fixture(root)
                document.update(change)
                (root / "saved.json").write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    load_suite(path)


if __name__ == "__main__":
    unittest.main()
