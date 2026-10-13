"""Phone recognition scores and corpus-source parsing fail closed on bad evidence."""

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_first_evaluation import read_run, score_sequences
from audio_first_reconciliation import preserve_spelling

spec = importlib.util.spec_from_file_location(
    "reading_benchmark",
    Path(__file__).resolve().parents[1] / "benchmark-reading-reconciliation.py",
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class ReferenceTests(unittest.TestCase):
    def test_musical_metadata_is_not_interpreted_as_lyric_source(self):
        for text in (
            "key:Bb maj\nBPM:90\n参考にしたアーティスト:Example",
            "sentence_id sentence yomi monophone\n001 空 ソラ s/o,r/a\n001 空 ソラ s/o,r/a",
        ):
            with self.assertRaises(ValueError):
                benchmark.parse_sentences(text)
        self.assertEqual(
            benchmark.parse_sentences(
                "sentence_id sentence yomi monophone\n001 空 ソラ s/o,r/a"
            ),
            {"pjs001": "空"},
        )

    def test_missing_predictions_are_errors_not_correct_abstentions(self):
        result = score_sequences(
            {"a": ["k", "a"], "b": ["i"]}, {"a": [], "b": ["u", "i"]}
        )
        self.assertEqual(
            (result["deletions"], result["insertions"], result["reference_phones"]),
            (2, 1, 3),
        )
        self.assertEqual(result["phone_error_rate"], 1.0)
        with self.assertRaises(ValueError):
            score_sequences({"a": ["i"]}, {})

    def test_homophonic_spelling_preserves_source_or_stays_ambiguous(self):
        self.assertEqual(
            preserve_spelling(["ろじょう", "ろぢょう"], "らじょう"), "ろじょう"
        )
        self.assertIsNone(preserve_spelling(["じ", "ぢ"], "し"))

    def test_receipt_authenticates_manifest_all_records_and_successful_heads(self):
        def sha(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case = {"id": "synthetic", "path": "audio.pcm"}
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"cases": [case]}))
            recipe = root / "recipe.json"
            recipe.write_text(
                json.dumps(
                    {
                        "engine": "whisper",
                        "manifest_sha256": sha(manifest),
                        "model": {"heads": {"whisper": {}}},
                    }
                )
            )
            row = root / "row.json"
            content = {
                "case": case,
                "recipe_sha256": sha(recipe),
                "failure": None,
                "heads": {"whisper": {"greedy": {"phones": ["a"]}}},
            }
            row.write_text(json.dumps(content))
            complete = root / "complete.json"

            def receipt():
                complete.write_text(
                    json.dumps(
                        {
                            "recipe_sha256": sha(recipe),
                            "records": [{"file": "row.json", "sha256": sha(row)}],
                        }
                    )
                )

            receipt()
            self.assertEqual(set(read_run(root, manifest)[1]), {"synthetic"})
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps({"text": "空"}))
            content.update(
                transcript="transcript.json", transcript_sha256=sha(transcript)
            )
            row.write_text(json.dumps(content))
            receipt()
            self.assertEqual(set(read_run(root, manifest)[1]), {"synthetic"})
            transcript.write_text(json.dumps({"text": "別の歌"}))
            with self.assertRaisesRegex(ValueError, "transcript"):
                read_run(root, manifest)
            content.pop("transcript")
            content.pop("transcript_sha256")
            content["heads"] = {}
            row.write_text(json.dumps(content))
            receipt()
            with self.assertRaisesRegex(ValueError, "head"):
                read_run(root, manifest)
            content["failure"] = "nonfinite"
            row.write_text(json.dumps(content))
            receipt()
            self.assertEqual(set(read_run(root, manifest)[1]), {"synthetic"})
            manifest.write_text("{}")
            with self.assertRaisesRegex(ValueError, "manifest"):
                read_run(root, manifest)


if __name__ == "__main__":
    unittest.main()
