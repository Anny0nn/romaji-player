"""Local configuration and model artifacts must stay out of public commits."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "export", Path(__file__).resolve().parents[1] / "check-export.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExportTests(unittest.TestCase):
    def test_local_configuration_is_rejected_at_any_depth(self):
        for path in [
            ".env",
            ".env.local",
            ".claude/skills/example/SKILL.md",
            "nested/.agents/skills/example/SKILL.md",
            "CLAUDE.md",
            "nested/AGENTS.md",
            "dist/RomajiPlayer.app/Contents/MacOS/RomajiPlayer",
            "tifa/model.pth",
            "data/lyrics.json",
        ]:
            with self.subTest(path=path):
                self.assertTrue(module.forbidden(path))

    def test_public_source_notices_and_empty_configuration_are_allowed(self):
        for path in [
            ".env.example",
            "src/study/alignment.rs",
            "refinement/refinement-model-files.json",
            "tifa/vendor/LICENSE",
            "build.rs",
            "aligner/synthetic-tone.ogg",
        ]:
            with self.subTest(path=path):
                self.assertFalse(module.forbidden(path))


if __name__ == "__main__":
    unittest.main()
