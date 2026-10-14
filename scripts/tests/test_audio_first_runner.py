"""Audio-only inputs cannot smuggle lyrics into blind recognition."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "blind_runner", Path(__file__).resolve().parents[1] / "recognize-singing-phones.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AudioOnlyManifest(unittest.TestCase):
    def case(self):
        return {
            "id": "test",
            "path": "audio.pcm",
            "sha256": "a" * 64,
            "encoding": "pcm",
            "first_sample": 0,
            "last_sample": 16000,
        }

    def test_source_text_reference_or_duplicate_identity_is_rejected(self):
        case = self.case()
        self.assertEqual(runner.manifest_cases({"version": 1, "cases": [case]}), [case])
        for key in ("raw_line", "words", "reference", "song_title"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "text"):
                runner.manifest_cases({"version": 1, "cases": [{**case, key: "私"}]})
        with self.assertRaises(ValueError):
            runner.manifest_cases({"version": 1, "cases": [case, case]})

    def test_bounds_and_encoding_are_not_inferred_from_lyric_content(self):
        for change in (
            {"first_sample": -1},
            {"last_sample": 0},
            {"first_sample": True},
            {"last_sample": 120 * 16000 + 1},
            {"encoding": "guessed"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.manifest_cases(
                    {"version": 1, "cases": [{**self.case(), **change}]}
                )


if __name__ == "__main__":
    unittest.main()
